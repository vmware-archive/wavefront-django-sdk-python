import platform

from django.apps import AppConfig
from django.conf import settings
from django.utils.module_loading import import_string

from wavefront_sdk.common import ApplicationTags


class WavefrontDjangoConfig(AppConfig):
    name = 'wavefront_django_sdk'
    verbose_name = 'Wavefront Django SDK'

    def ready(self):
        self.setup_wavefront_reporter()
        try:
            self.application_tags = ApplicationTags(**getattr(settings, 'WF_APPLICATION_TAGS'))
        except AttributeError:
            raise ValueError('"WF_APPLICATION_TAGS" setting is required by wavefront_django_sdk.')
        self.setup_tracer()

    def setup_tracer(self):
        tracer_class = getattr(
            settings,
            'OPENTRACING_TRACER_CALLABLE',
            'wavefront_django_sdk.tracing.DjangoTracing'
        )
        if not callable(tracer_class):
            tracer_class = import_string(tracer_class)

        tracer_parameters = getattr(settings, 'OPENTRACING_TRACER_PARAMETERS', {})
        self.tracing = tracer_class(**tracer_parameters)

    def setup_wavefront_reporter(self):
        reporter_class = getattr(
            settings,
            'WF_REPORTER',
            'wavefront_pyformance.wavefront_reporter.WavefrontDirectReporter'
        )
        if not callable(reporter_class):
            reporter_class = import_string(reporter_class)

        reporter_kwargs = getattr(settings, 'WF_REPORTER_CONFIG', {})
        reporter_kwargs.setdefault('source', platform.uname()[1])

        try:
            self.reporter = reporter_class(**reporter_kwargs).report_minute_distribution()
        except TypeError:
            raise ValueError('"WF_REPORTER_CONFIG" setting value is invalid.')

        granularity = getattr(settings, 'WF_REPORTER_GRANULARITY', 'minute')
        try:
            getattr(self.reporter, 'report_{}_distribution'.format(granularity))()
        except AttributeError:
            raise ValueError(
                '"{granularity}" is not valid value for WF_REPORTER_GRANULARITY'
                .format(granularity=getattr(
                    settings,
                    'WF_REPORTER_GRANULARITY',
                    ''
                ))
            )
