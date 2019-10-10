"""
Wavefront Django Middleware.

@author: Hao Song (songhao@vmware.com)
"""
import logging
import math
import os
import platform
import time
from timeit import default_timer

from django.conf import settings
from django.urls import resolve
from django.utils.deprecation import MiddlewareMixin
from django.utils.module_loading import import_string

from django_opentracing import DjangoTracing

import opentracing

from wavefront_django_sdk.constants import DJANGO_COMPONENT, NULL_TAG_VAL, \
    REPORTER_PREFIX, REQUEST_PREFIX, RESPONSE_PREFIX, WAVEFRONT_PROVIDED_SOURCE

from wavefront_opentracing_sdk import reporting
from wavefront_opentracing_sdk.tracer import WavefrontTracer

from wavefront_pyformance.delta import delta_counter
from wavefront_pyformance.tagged_registry import TaggedRegistry
from wavefront_pyformance.wavefront_histogram import wavefront_histogram
from wavefront_pyformance.wavefront_reporter import WavefrontReporter

from wavefront_sdk.common import ApplicationTags, HeartbeaterService


# pylint: disable=invalid-name, protected-access, too-many-instance-attributes
class WavefrontMiddleware(MiddlewareMixin):
    """Wavefront Django Middleware."""

    def __init__(self, get_response=None):
        """Construct Wavefront Django Middleware.

        :param get_response: Method to get response
        """
        super(WavefrontMiddleware, self).__init__(get_response)
        logging.basicConfig(level=logging.INFO)
        self.reporter = self.get_reporter()
        self.logger = logging.getLogger(__name__)
        self.MIDDLEWARE_ENABLED = False
        try:
            self.is_debug = self.get_conf('WF_DEBUG') or False
            if not self.reporter or (not isinstance(
                    self.reporter, WavefrontReporter) and not self.is_debug):
                raise AttributeError(
                    "WF_REPORTER not correctly configured!")
            elif not isinstance(self.application_tags, ApplicationTags):
                raise AttributeError(
                    "WF_APPLICATION_TAGS not correctly configured!")
            elif not isinstance(self.tracing, DjangoTracing):
                raise AttributeError(
                    "OPENTRACING_TRACING not correctly configured!")
            else:
                self.APPLICATION = self.application_tags.application or \
                                   NULL_TAG_VAL
                self.CLUSTER = self.application_tags.cluster or NULL_TAG_VAL
                self.SERVICE = self.application_tags.service or NULL_TAG_VAL
                self.SHARD = self.application_tags.shard or NULL_TAG_VAL
                self.reg = None
                if self.is_debug:
                    self.reg = self.get_conf('DEBUG_REGISTRY')
                self.reg = self.reg or TaggedRegistry()
                self.reporter.registry = self.reg
                if not self.get_conf('WF_DISABLE_REPORTING') \
                        and hasattr(self.reporter, 'start'):
                    self.reporter.start()
                    self.heartbeaterService = HeartbeaterService(
                        wavefront_client=self.reporter.wavefront_client,
                        application_tags=self.application_tags,
                        components=DJANGO_COMPONENT,
                        source=self.reporter.source)
                self.tracing._trace_all = getattr(settings,
                                                  'OPENTRACING_TRACE_ALL',
                                                  True)
                opentracing.set_global_tracer(self.tracing.tracer)
                self.MIDDLEWARE_ENABLED = True
        except AttributeError as e:
            self.logger.warning(e)
        finally:
            if not self.MIDDLEWARE_ENABLED:
                self.logger.warning("Wavefront Django Middleware not enabled!")

    def __del__(self):
        """Destruct Wavefront Django Middleware."""
        if self.reporter and hasattr(self.reporter, 'stop'):
            self.reporter.stop()
        if getattr(self, 'heartbeaterService', None):
            self.heartbeaterService.close()

    # pylint: disable=unused-argument
    def process_view(self, request, view_func, view_args, view_kwargs):
        """
        Process the view before Django calls.

        :param request: incoming HTTP request.
        :param view_func: function that Django is about to use.
        :param view_args: list of positional arguments passed to the view.
        :param view_kwargs: dictionary of keyword arguments passed to the view.
        """
        if not self.MIDDLEWARE_ENABLED:
            return
        request.wf_start_timestamp = default_timer()
        request.wf_cpu_nanos = time.clock()

        entity_name = self.get_entity_name(request)
        func_name = resolve(request.path_info).func.__name__
        module_name = resolve(request.path_info).func.__module__
        self.update_gauge(
            registry=self.reg,
            key=self.get_metric_name(entity_name, request) + ".inflight",
            tags=self.get_tags_map(module_name=module_name,
                                   func_name=func_name),
            val=1
        )
        self.update_gauge(
            registry=self.reg,
            key="total_requests.inflight",
            tags=self.get_tags_map(
                cluster=self.CLUSTER,
                service=self.SERVICE,
                shard=self.SHARD),
            val=1
        )
        if self.tracing:
            if not self.tracing._trace_all:
                return
            if hasattr(settings, 'OPENTRACING_TRACED_ATTRIBUTES'):
                traced_attributes = getattr(settings,
                                            'OPENTRACING_TRACED_ATTRIBUTES')
            else:
                traced_attributes = []
            self.tracing._apply_tracing(request, view_func, traced_attributes)

    # pylint: disable=too-many-locals
    def process_response(self, request, response):
        """
        Process the response before Django calls.

        :param request: incoming HTTP request.
        :param response: outgoing response.
        """
        if not self.MIDDLEWARE_ENABLED:
            return response
        entity_name = self.get_entity_name(request)
        func_name = resolve(request.path_info).func.__name__
        module_name = resolve(request.path_info).func.__module__

        if self.tracing:
            self.tracing._finish_tracing(request, response=response)

        self.update_gauge(
            registry=self.reg,
            key=self.get_metric_name(entity_name, request) + ".inflight",
            tags=self.get_tags_map(
                module_name=module_name,
                func_name=func_name),
            val=-1
        )
        self.update_gauge(
            registry=self.reg,
            key="total_requests.inflight",
            tags=self.get_tags_map(
                cluster=self.CLUSTER,
                service=self.SERVICE,
                shard=self.SHARD),
            val=-1
        )

        response_metric_key = self.get_metric_name(entity_name, request,
                                                   response)

        complete_tags_map = self.get_tags_map(
            cluster=self.CLUSTER,
            service=self.SERVICE,
            shard=self.SHARD,
            module_name=module_name,
            func_name=func_name
        )

        aggregated_per_shard_map = self.get_tags_map(
            cluster=self.CLUSTER,
            service=self.SERVICE,
            shard=self.SHARD,
            module_name=module_name,
            func_name=func_name,
            source=WAVEFRONT_PROVIDED_SOURCE)

        overall_aggregated_per_source_map = self.get_tags_map(
            cluster=self.CLUSTER,
            service=self.SERVICE,
            shard=self.SHARD)

        overall_aggregated_per_shard_map = self.get_tags_map(
            cluster=self.CLUSTER,
            service=self.SERVICE,
            shard=self.SHARD,
            source=WAVEFRONT_PROVIDED_SOURCE)

        aggregated_per_service_map = self.get_tags_map(
            cluster=self.CLUSTER,
            service=self.SERVICE,
            module_name=module_name,
            func_name=func_name,
            source=WAVEFRONT_PROVIDED_SOURCE)

        overall_aggregated_per_service_map = self.get_tags_map(
            cluster=self.CLUSTER,
            service=self.SERVICE,
            source=WAVEFRONT_PROVIDED_SOURCE)

        aggregated_per_cluster_map = self.get_tags_map(
            cluster=self.CLUSTER,
            module_name=module_name,
            func_name=func_name,
            source=WAVEFRONT_PROVIDED_SOURCE)

        overall_aggregated_per_cluster_map = self.get_tags_map(
            cluster=self.CLUSTER,
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
        # django.server.response.style._id_.make.GET.errors
        self.reg.counter(response_metric_key + ".cumulative",
                         tags=complete_tags_map).inc()
        if self.application_tags.shard:
            delta_counter(
                self.reg, response_metric_key + ".aggregated_per_shard",
                tags=aggregated_per_shard_map).inc()
        delta_counter(
            self.reg, response_metric_key + ".aggregated_per_service",
            tags=aggregated_per_service_map).inc()
        if self.application_tags.cluster:
            delta_counter(
                self.reg, response_metric_key + ".aggregated_per_cluster",
                tags=aggregated_per_cluster_map).inc()
        delta_counter(
            self.reg, response_metric_key + ".aggregated_per_application",
            tags=aggregated_per_application_map).inc()

        # django.server.response.errors.aggregated_per_source.count
        # django.server.response.errors.aggregated_per_shard.count
        # django.server.response.errors.aggregated_per_service.count
        # django.server.response.errors.aggregated_per_cluster.count
        # django.server.response.errors.aggregated_per_application.count
        if self.is_error_status_code(response):
            self.reg.counter(
                self.get_metric_name_without_status(entity_name, request),
                tags=complete_tags_map).inc()
            self.reg.counter("response.errors", tags=complete_tags_map).inc()
            self.reg.counter("response.errors.aggregated_per_source",
                             tags=overall_aggregated_per_source_map).inc()
            if self.application_tags.shard:
                delta_counter(self.reg, "response.errors.aggregated_per_shard",
                              tags=overall_aggregated_per_shard_map).inc()
            delta_counter(self.reg, "response.errors.aggregated_per_service",
                          tags=overall_aggregated_per_service_map).inc()
            if self.application_tags.cluster:
                delta_counter(self.reg,
                              "response.errors.aggregated_per_cluster",
                              tags=overall_aggregated_per_cluster_map).inc()
            delta_counter(self.reg,
                          "response.errors.aggregated_per_application",
                          tags=overall_aggregated_per_application_map).inc()

        # django.server.response.completed.aggregated_per_source.count
        # django.server.response.completed.aggregated_per_shard.count
        # django.server.response.completed.aggregated_per_service.count
        # django.server.response.completed.aggregated_per_cluster.count
        # django.server.response.completed.aggregated_per_application.count
        self.reg.counter("response.completed.aggregated_per_source",
                         tags=overall_aggregated_per_source_map).inc()
        if self.SHARD is not NULL_TAG_VAL:
            delta_counter(
                self.reg, "response.completed.aggregated_per_shard",
                tags=overall_aggregated_per_shard_map).inc()
            self.reg.counter("response.completed.aggregated_per_service",
                             tags=overall_aggregated_per_service_map).inc()
        if self.CLUSTER is not NULL_TAG_VAL:
            delta_counter(
                self.reg, "response.completed.aggregated_per_cluster",
                tags=overall_aggregated_per_cluster_map).inc()
            self.reg.counter("response.completed.aggregated_per_application",
                             tags=overall_aggregated_per_application_map).inc()

        # django.server.response.style._id_.make.summary.GET.200.latency.m
        # django.server.response.style._id_.make.summary.GET.200.cpu_ns.m
        # django.server.response.style._id_.make.summary.GET.200.total_time.count
        if hasattr(request, 'wf_start_timestamp'):
            timestamp_duration = default_timer() - request.wf_start_timestamp
            cpu_nanos_duration = time.clock() - request.wf_cpu_nanos
            wavefront_histogram(self.reg, response_metric_key + ".latency",
                                tags=complete_tags_map).add(timestamp_duration)
            wavefront_histogram(self.reg, response_metric_key + ".cpu_ns",
                                tags=complete_tags_map).add(cpu_nanos_duration)
            self.reg.counter(response_metric_key + ".total_time",
                             tags=complete_tags_map).inc(timestamp_duration)
        return response

    # pylint: disable=too-many-arguments
    def get_tags_map(self, cluster=None, service=None, shard=None,
                     module_name=None, func_name=None, source=None):
        """Get tags of span as dict.

        :param cluster: Cluster from application tags.
        :param service: Service from application tags.
        :param shard: Shard from application tags.
        :param module_name: Name of Django module.
        :param func_name: Name of Django func
        :param source: Name of source.
        :return: tags of span.
        """
        tags_map = {'application': self.APPLICATION}
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

    @property
    def application_tags(self):
        if not hasattr(self, '_application_tags'):
            self._application_tags = ApplicationTags(
                **self.get_conf('WF_APPLICATION_TAGS', {})
            )
        return self._application_tags

    @classmethod
    def get_reporter(cls):
        """
        The reporter is stored on the class to avoid the
        possibility of multiple clients.
        :return:
        """
        if not hasattr(cls, '_reporter'):
            reporter_class = cls.get_conf(
                'WF_REPORTER',
                'wavefront_opentracing_sdk.reporting.ConsoleReporter'
            )
            if not callable(reporter_class):
                reporter_class = import_string(reporter_class)
            reporter_kwargs = getattr(settings, 'WF_REPORTER_CONFIG', {})
            reporter_kwargs.setdefault('source', platform.uname()[1])

            try:
                cls._reporter = reporter_class(**reporter_kwargs)
            except TypeError:
                raise AttributeError(
                    '"WF_REPORTER_CONFIG" setting value is invalid for selected reporter!'   # noqa E501
                )

            granularity = cls.get_conf('WF_HISTOGRAM_GRANULARITY', 'minute')
            if granularity is not None:
                try:
                    getattr(cls._reporter,
                            'report_{}_distribution'.format(granularity)
                            )()
                except AttributeError:
                    raise ValueError(
                        'The selected reporter does not support "{granularity}" WF_HISTOGRAM_GRANULARITY'  # noqa E501
                        .format(granularity=granularity)
                    )

            cls._reporter.prefix = REPORTER_PREFIX
        return cls._reporter

    @property
    def tracing(self):
        if not hasattr(self, '_tracing'):
            opentracing_class = self.get_conf(
                'OPENTRACING_TRACER_CALLABLE',
                'wavefront_django_sdk.tracing.DjangoTracing'
            )
            kwargs = self.get_conf('OPENTRACING_TRACER_PARAMETERS', {})

            if not callable(opentracing_class):
                opentracing_class = import_string(opentracing_class)

            self._tracing = opentracing_class(self.get_tracer(), **kwargs)
        return self._tracing

    def initialize_span_reporter(self, span_reporter_class):
        if not callable(span_reporter_class):
            span_reporter_class = import_string(span_reporter_class)
        kwargs = {
            'source': getattr(self.reporter, 'source', platform.uname()[1])
        }
        if issubclass(span_reporter_class, reporting.WavefrontSpanReporter):
            try:
                kwargs['client'] = self.reporter.wavefront_client
            except AttributeError:
                message = '"WavefrontSpanReporter" may only be used with a reporter from "wavefront_pyformance"'  # noqa E501
                if self.is_debug:
                    self.logger.warning(message)
                else:
                    raise AttributeError(message)
        return span_reporter_class(**kwargs)

    def get_span_reporter(self):
        if not hasattr(self, '_span_reporter'):
            span_reporter_class = self.get_conf(
                'WF_SPAN_REPORTER',
                'wavefront_opentracing_sdk.reporting.WavefrontSpanReporter'
            )
            if hasattr(span_reporter_class, '__iter__'):
                # If the setting is iterable, make a composite reporter
                span_reporters = [
                    self.initialize_span_reporter(span_reporter)
                    for span_reporter
                    in span_reporter_class
                ]
                self._span_reporter = reporting.CompositeReporter(
                    *span_reporters)
            else:
                self._span_reporter = self.initialize_span_reporter(
                    span_reporter_class)
        return self._span_reporter

    def get_tracer(self, **kwargs):
        if opentracing.is_global_tracer_registered() and \
                isinstance(opentracing.global_tracer(), WavefrontTracer):
            return opentracing.global_tracer()
        else:
            return WavefrontTracer(
                reporter=self.get_span_reporter(),
                application_tags=self.application_tags,
                **self.get_conf('OPENTRACING_TRACER_PARAMETERS', {})
            )

    @staticmethod
    def get_entity_name(request):
        """Get entity name from the request.

        :param request: Http request.
        :return: Entity name.
        """
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
        """Get metric name.

        :param entity_name: Entity Name.
        :param request: Http request.
        :param response: Response obj.
        :return: Metric name.
        """
        metric_name = [entity_name, request.method]
        if response:
            metric_name.insert(0, RESPONSE_PREFIX)
            metric_name.append(str(response.status_code))
        else:
            metric_name.insert(0, REQUEST_PREFIX)
        return '.'.join(metric_name)

    @staticmethod
    def get_metric_name_without_status(entity_name, request):
        """Get metric name w/o response.

        :param entity_name: Entity Name.
        :param request: Http request.
        :return: Metric name
        """
        metric_name = [entity_name, request.method]
        metric_name.insert(0, REQUEST_PREFIX)
        return '.'.join(metric_name)

    @staticmethod
    def is_error_status_code(response):
        """Check is response status code is error or not.

        :param response: Response obj
        :return: Is error response code or not.
        """
        return 400 <= response.status_code <= 599

    @staticmethod
    def update_gauge(registry, key, tags, val):
        """Update gauge value.

        :param registry: TaggedRegistry from pyformance.
        :param key: Key of the gauge.
        :param tags: Tags of the gauge.
        :param val: Value of the gauge.
        """
        gauge = registry.gauge(key=key, tags=tags)
        cur_val = gauge.get_value()
        if math.isnan(cur_val):
            cur_val = 0
        gauge.set_value(cur_val + val)

    @staticmethod
    def get_conf(key, default=None):
        """Get configuration from settings or env.

        :param key: Key of the configuration.
        :return: Value of the configuration.
        """
        if hasattr(settings, key):
            return settings.__getattr__(key)
        if key in os.environ:
            return os.environ[key]
        return default
