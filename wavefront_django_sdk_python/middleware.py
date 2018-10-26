import os
import time
import math
import logging
from timeit import default_timer
from django.urls import resolve
from django.conf import settings
from wavefront_pyformance.wavefront_reporter import WavefrontReporter
from wavefront_pyformance.tagged_registry import TaggedRegistry
from wavefront_pyformance.delta import delta_counter
from wavefront_django_sdk_python.heartbeater_service import HeartbeaterService
from wavefront_django_sdk_python.application_tags import ApplicationTags
from wavefront_django_sdk_python.constants import NULL_TAG_VAL, \
    WAVEFRONT_PROVIDED_SOURCE, RESPONSE_PREFIX, REQUEST_PREFIX, \
    REPORTER_PREFIX, DJANGO_COMPONENT, HEART_BEAT_INTERVAL

try:
    # Django >= 1.10
    from django.utils.deprecation import MiddlewareMixin
except ImportError:
    # Not required for Django <= 1.9, see:
    MiddlewareMixin = object

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_conf(key):
    if hasattr(settings, key):
        return settings.__getattr__(key)
    if key in os.environ:
        return os.environ[key]
    return None


MIDDLEWARE_ENABLED = False
try:
    reporter = get_conf('WF_REPORTER')
    application_tags = get_conf('APPLICATION_TAGS')
    if not isinstance(reporter, WavefrontReporter):
        raise AttributeError(
            "WF_REPORTER not correctly configured in settings.py!")
    elif not isinstance(application_tags, ApplicationTags):
        raise AttributeError(
            "APPLICATION_TAGS not correctly configured in settings.py!")
    else:
        APPLICATION = application_tags.application or NULL_TAG_VAL
        CLUSTER = application_tags.cluster or NULL_TAG_VAL
        SERVICE = application_tags.service or NULL_TAG_VAL
        SHARD = application_tags.shard or NULL_TAG_VAL
        reporter.prefix = REPORTER_PREFIX
        reg = TaggedRegistry()
        reporter.registry = reg
        reporter.start()
        heartbeaterService = HeartbeaterService(
            wavefront_client=reporter.wavefront_client,
            application_tags=application_tags,
            component=DJANGO_COMPONENT,
            source=reporter.source,
            reporting_interval_seconds=HEART_BEAT_INTERVAL)
        MIDDLEWARE_ENABLED = True
except AttributeError as e:
    logger.warning(e)
finally:
    if not MIDDLEWARE_ENABLED:
        logger.warning("Wavefront Django Middleware not enabled!")


class WavefrontMiddleware(MiddlewareMixin):

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not MIDDLEWARE_ENABLED:
            return
        request.wf_start_timestamp = default_timer()
        request.wf_cpu_nanos = time.clock()

        entity_name = self.get_entity_name(request)
        func_name = resolve(request.path_info).func.__name__
        module_name = resolve(request.path_info).func.__module__
        self.update_gauge(
            registry=reg,
            key=self.get_metric_name(entity_name, request) + ".inflight",
            tags=self.get_tags_map(
                module_name=module_name,
                func_name=func_name),
            val=1
        )
        self.update_gauge(
            registry=reg,
            key="total_requests.inflight",
            tags=self.get_tags_map(
                cluster=CLUSTER,
                service=SERVICE,
                shard=SHARD),
            val=1
        )

    def process_response(self, request, response):
        if not MIDDLEWARE_ENABLED:
            return response
        entity_name = self.get_entity_name(request)
        func_name = resolve(request.path_info).func.__name__
        module_name = resolve(request.path_info).func.__module__

        self.update_gauge(
            registry=reg,
            key=self.get_metric_name(entity_name, request) + ".inflight",
            tags=self.get_tags_map(
                module_name=module_name,
                func_name=func_name),
            val=-1
        )
        self.update_gauge(
            registry=reg,
            key="total_requests.inflight",
            tags=self.get_tags_map(
                cluster=CLUSTER,
                service=SERVICE,
                shard=SHARD),
            val=-1
        )

        response_metric_key = self.get_metric_name(entity_name, request,
                                                   response)

        complete_tags_map = self.get_tags_map(
            cluster=CLUSTER,
            service=SERVICE,
            shard=SHARD,
            module_name=module_name,
            func_name=func_name
        )

        aggregated_per_shard_map = self.get_tags_map(
            cluster=CLUSTER,
            service=SERVICE,
            shard=SHARD,
            module_name=module_name,
            func_name=func_name,
            source=WAVEFRONT_PROVIDED_SOURCE)

        overall_aggregated_per_source_map = self.get_tags_map(
            cluster=CLUSTER,
            service=SERVICE,
            shard=SHARD)

        overall_aggregated_per_shard_map = self.get_tags_map(
            cluster=CLUSTER,
            service=SERVICE,
            shard=SHARD,
            source=WAVEFRONT_PROVIDED_SOURCE)

        aggregated_per_service_map = self.get_tags_map(
            cluster=CLUSTER,
            service=SERVICE,
            module_name=module_name,
            func_name=func_name,
            source=WAVEFRONT_PROVIDED_SOURCE)

        overall_aggregated_per_service_map = self.get_tags_map(
            cluster=CLUSTER,
            service=SERVICE,
            source=WAVEFRONT_PROVIDED_SOURCE)

        aggregated_per_cluster_map = self.get_tags_map(
            cluster=CLUSTER,
            module_name=module_name,
            func_name=func_name,
            source=WAVEFRONT_PROVIDED_SOURCE)

        overall_aggregated_per_cluster_map = self.get_tags_map(
            cluster=CLUSTER,
            source=WAVEFRONT_PROVIDED_SOURCE)

        aggregated_per_application_map = self.get_tags_map(
            module_name=module_name,
            func_name=func_name,
            source=WAVEFRONT_PROVIDED_SOURCE
        )

        overall_aggregated_per_application_map = self.get_tags_map(
            source=WAVEFRONT_PROVIDED_SOURCE)

        # django.server.response.style._id_.make.GET.200.cumulative.count
        # django.server.response.style._id_.make.GET.200.aggregated_per_shard.count
        # django.server.response.style._id_.make.GET.200.aggregated_per_service.count
        # django.server.response.style._id_.make.GET.200.aggregated_per_cluster.count
        # django.server.response.style._id_.make.GET.200.aggregated_per_application.count
        reg.counter(response_metric_key + ".cumulative",
                    tags=complete_tags_map).inc()
        if application_tags.shard:
            delta_counter(
                reg, response_metric_key + ".aggregated_per_shard",
                tags=aggregated_per_shard_map).inc()
        delta_counter(
            reg, response_metric_key + ".aggregated_per_service",
            tags=aggregated_per_service_map).inc()
        if application_tags.cluster:
            delta_counter(
                reg, response_metric_key + ".aggregated_per_cluster",
                tags=aggregated_per_cluster_map).inc()
        delta_counter(
            reg, response_metric_key + ".aggregated_per_application",
            tags=aggregated_per_application_map).inc()

        # django.server.response.style._id_.make.summary.GET.200.latency.m
        # django.server.response.style._id_.make.summary.GET.200.cpu_ns.m
        if hasattr(request, 'wf_start_timestamp'):
            timestamp_duration = default_timer() - request.wf_start_timestamp
            cpu_nanos_duration = time.clock() - request.wf_cpu_nanos
            reg.histogram(response_metric_key + ".latency",
                          tags=complete_tags_map).add(timestamp_duration)
            reg.histogram(response_metric_key + ".cpu_ns",
                          tags=complete_tags_map).add(cpu_nanos_duration)

        # django.server.response.errors.aggregated_per_source.count
        # django.server.response.errors.aggregated_per_shard.count
        # django.server.response.errors.aggregated_per_service.count
        # django.server.response.errors.aggregated_per_cluster.count
        # django.server.response.errors.aggregated_per_application.count
        if self.is_error_status_code(response):
            reg.counter("response.errors", tags=complete_tags_map)
            reg.counter("response.errors.aggregated_per_source",
                        tags=overall_aggregated_per_source_map)
            if application_tags.shard:
                delta_counter(reg, "response.errors.aggregated_per_shard",
                              tags=overall_aggregated_per_shard_map)
            delta_counter(reg, "response.errors.aggregated_per_service",
                          tags=overall_aggregated_per_service_map)
            if application_tags.cluster:
                delta_counter(reg, "response.errors.aggregated_per_cluster",
                              tags=overall_aggregated_per_cluster_map)
            delta_counter(reg, "response.errors.aggregated_per_application",
                          tags=overall_aggregated_per_application_map)

        # django.server.response.completed.aggregated_per_source.count
        # django.server.response.completed.aggregated_per_shard.count
        # django.server.response.completed.aggregated_per_service.count
        # django.server.response.completed.aggregated_per_cluster.count
        # django.server.response.completed.aggregated_per_application.count
        reg.counter("response.completed.aggregated_per_source",
                    tags=overall_aggregated_per_source_map).inc()
        if SHARD is not NULL_TAG_VAL:
            delta_counter(
                reg, "response.completed.aggregated_per_shard",
                tags=overall_aggregated_per_shard_map).inc()
        reg.counter("response.completed.aggregated_per_service",
                    tags=overall_aggregated_per_service_map).inc()
        if CLUSTER is not NULL_TAG_VAL:
            delta_counter(
                reg, "response.completed.aggregated_per_cluster",
                tags=overall_aggregated_per_cluster_map).inc()
        reg.counter("response.completed.aggregated_per_application",
                    tags=overall_aggregated_per_application_map).inc()
        return response

    @staticmethod
    def get_tags_map(cluster=None, service=None, shard=None, module_name=None,
                     func_name=None, source=None):
        tags_map = {}
        if cluster:
            tags_map['cluster'] = cluster
        if service:
            tags_map['service'] = service
        if shard:
            tags_map['shard'] = shard
        if module_name:
            tags_map['django.resource.module'] = module_name
        if func_name:
            tags_map['django.resource.func'] = func_name
        if source:
            tags_map['source'] = source
        return tags_map

    @staticmethod
    def get_entity_name(request):
        resolver_match = request.resolver_match
        if resolver_match:
            entity_name = resolver_match.url_name
            if not entity_name:
                entity_name = resolver_match.view_name
            entity_name = entity_name.replace('-', '_').replace('/', '.'). \
                replace('{', '_').replace('}', '_')
        else:
            entity_name = 'UNKNOWN'
        return entity_name.lstrip('.').rstrip('.')

    @staticmethod
    def get_metric_name(entity_name, request, response=None):
        metric_name = [entity_name, request.method]
        if response:
            metric_name.insert(0, RESPONSE_PREFIX)
            metric_name.append(str(response.status_code))
        else:
            metric_name.insert(0, REQUEST_PREFIX)
        return '.'.join(metric_name)

    @staticmethod
    def is_error_status_code(response):
        return 400 <= response.status_code <= 599

    @staticmethod
    def update_gauge(registry, key, tags, val):
        gauge = registry.gauge(key=key, tags=tags)
        cur_val = gauge.get_value()
        if math.isnan(cur_val):
            cur_val = 0
        gauge.set_value(cur_val + val)
