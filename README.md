```
VMware has ended active development of this project, this repository will no longer be updated.
```

# Wavefront Django SDK

This SDK provides support for reporting out of the box metric, histograms and tracing from your Django based  application. That data is reported to Wavefront via proxy or direct ingestion. That data will help you understand how your application is performing in production.

## Install

```bash
pip install wavefront_django_sdk_python
```

## Usage

Configure *settings.py* of your application to install Django SDK as follows:

 ```python
# setting.py

from wavefront_pyformance.wavefront_reporter import WavefrontDirectReporter, WavefrontProxyReporter
from wavefront_sdk.common import ApplicationTags
from wavefront_django_sdk import DjangoTracing
from wavefront_opentracing_sdk import reporting, WavefrontTracer

INSTALLED_APPS = [
    '...',
    'wavefront_django_sdk',
    '...'
]
 
MIDDLEWARE = [
    'wavefront_django_sdk.middleware.WavefrontMiddleware',
    '...'
]

SOURCE = "{SOURCE}"

APPLICATION_TAGS = ApplicationTags(
    application="{APP_NAME}",
    service="{SERVICE_NAME}",
    cluster="{CLUSTER_NAME}",  # Optional
    shard="{SHARD_NAME}," , # Optional
    custom_tags=[("location", "Oregon"), ("env", "Staging")]  # Optional
)

# Sending data via Direct Ingestion
WF_REPORTER = WavefrontDirectReporter(
    server="{ADDRESS}",
    token="{TOKEN}",
    reporting_interval=5,  # Optional, default value is 10 secs
    source=SOURCE,
    tags={"application": APPLICATION_TAGS.application}
).report_minute_distribution()

# Or, Sending data via Proxy
WF_REPORTER = WavefrontProxyReporter(
    host="{HOST}",
    port=2878,  # Optional, Wavefront Proxy running on 2878 by default
    reporting_interval=5,  # Optional, default value is 10 secs
    source=SOURCE,
    tags={"application": APPLICATION_TAGS.application}
).report_minute_distribution()

span_reporter = reporting.WavefrontSpanReporter(
    client=WF_REPORTER.wavefront_client,
    source=SOURCE,
)

OPENTRACING_TRACE_ALL = True  # Optional, default value is False

OPENTRACING_TRACING = DjangoTracing(WavefrontTracer(
    reporter=span_reporter, application_tags=APPLICATION_TAGS))

 ```

## Out of the box metrics and histograms for your Django based application.

 Assume you have the following API in your Django Application:

```python
# urls.py
from django.urls import path
from . import views
 
urlpatterns = [
    path('style/<slug:id>/make', views.make_shirts, name="style/{id}/make")
]
 
# view.py
from django.http import HttpResponse
 
def make_shirts(request, id):
    return HttpResponse("completed", status=200)
```

### Request Gauges

| Entity Name                                       | Entity Type | source | application | cluster   | service | shard   | django.resource.module | django.resource.func |
| :------------------------------------------------ | :---------- | :----- | :---------- | :-------- | :------ | :------ | :--------------------- | :------------------- |
| django.request.style._id_.make.GET.inflight.value | Gauge       | host-1 | Ordering    | us-west-1 | styling | primary | styling.views          | make_shirts          |
| django.total_requests.inflight.value              | Gauge       | host-1 | Ordering    | us-west-1 | styling | primary | n/a                    | n/a                  |

### Granular Response related metrics

| Entity Name                                                  | Entity Type  | source             | application | cluster   | service | shard   | django.resource.module | django.resource.func |
| :----------------------------------------------------------- | :----------- | :----------------- | :---------- | :-------- | :------ | :------ | :--------------------- | :------------------- |
| django.response.style.\_id_.make.GET.200.cumulative.count    | Counter      | host-1             | Ordering    | us-west-1 | styling | primary | styling.views          | make_shirts          |
| django.response.style.\_id_.make.GET.200.aggregated_per_shard.count | DeltaCounter | wavefront-provided | Ordering    | us-west-1 | styling | primary | styling.views          | make_shirts          |
| django.response.style.\_id_.make.GET.200.aggregated_per_service.count | DeltaCounter | wavefront-provided | Ordering    | us-west-1 | styling | n/a     | styling.views          | make_shirts          |
| django.response.style.\_id_.make.GET.200.aggregated_per_cluster.count | DeltaCounter | wavefront-provided | Ordering    | us-west-1 | n/a     | n/a     | styling.views          | make_shirts          |
| django.response.style.\_id_.make.GET.200.aggregated_per_application.count | DeltaCounter | wavefront-provided | Ordering    | n/a       | n/a     | n/a     | styling.views          | make_shirts          |

### Granular Response related histograms

| Entity Name                                                | Entity Type        | source | application | cluster   | service | shard   | django.resource.module | django.resource.func |
| :--------------------------------------------------------- | :----------------- | :----- | :---------- | :-------- | :------ | :------ | :--------------------- | :------------------- |
| django.response.style.\_id_.make.summary.GET.200.latency.m | WavefrontHistogram | host-1 | Ordering    | us-west-1 | styling | primary | styling.views          | make_shirts          |
| django.response.style.\_id_.make.summary.GET.200.cpu_ns.m  | WavefrontHistogram | host-1 | Ordering    | us-west-1 | styling | primary | styling.views          | make_shirts          |

### Overall Response related metrics

This includes all the completed requests that returned a response (i.e. success + errors).

| Entity Name                                                | Entity Type  | source            | application | cluster   | service | shard   |
| :--------------------------------------------------------- | :----------- | :---------------- | :---------- | :-------- | :------ | :------ |
| django.response.completed.aggregated_per_source.count      | Counter      | host-1            | Ordering    | us-west-1 | styling | primary |
| django.response.completed.aggregated_per_shard.count       | DeltaCounter | wavefont-provided | Ordering    | us-west-1 | styling | primary |
| django.response.completed.aggregated_per_service.count     | DeltaCounter | wavefont-provided | Ordering    | us-west-1 | styling | n/a     |
| django.response.completed.aggregated_per_cluster.count     | DeltaCounter | wavefont-provided | Ordering    | us-west-1 | n/a     | n/a     |
| django.response.completed.aggregated_per_application.count | DeltaCounter | wavefont-provided | Ordering    | n/a       | n/a     | n/a     |

### Overall Error Response related metrics

This includes all the completed requests that resulted in an error response (that is HTTP status code of 4xx or 5xx).

| Entity Name                                             | Entity Type  | source            | application | cluster   | service | shard   |
| :------------------------------------------------------ | :----------- | :---------------- | :---------- | :-------- | :------ | :------ |
| django.response.errors.aggregated_per_source.count      | Counter      | host-1            | Ordering    | us-west-1 | styling | primary |
| django.response.errors.aggregated_per_shard.count       | DeltaCounter | wavefont-provided | Ordering    | us-west-1 | styling | primary |
| django.response.errors.aggregated_per_service.count     | DeltaCounter | wavefont-provided | Ordering    | us-west-1 | styling | n/a     |
| django.response.errors.aggregated_per_cluster.count     | DeltaCounter | wavefont-provided | Ordering    | us-west-1 | n/a     | n/a     |
| django.response.errors.aggregated_per_application.count | DeltaCounter | wavefont-provided | Ordering    | n/a       | n/a     | n/a     |

### Tracing Spans

Every span will have the operation name as span name, start time in millisec along with duration in millisec. The following table includes all the rest attributes of generated tracing spans.  

| Span Tag Key           | Span Tag Value                       |
| ---------------------- | ------------------------------------ |
| traceId                | 4a3dc181-d4ac-44bc-848b-133bb3811c31 |
| parent                 | q908ddfe-4723-40a6-b1d3-1e85b60d9016 |
| followsFrom            | b768ddfe-4723-40a6-b1d3-1e85b60d9016 |
| spanId                 | c908ddfe-4723-40a6-b1d3-1e85b60d9016 |
| component              | django                               |
| span.kind              | server                               |
| application            | Ordering                             |
| service                | styling                              |
| cluster                | us-west-1                            |
| shard                  | primary                              |
| location               | Oregon (*custom tag)                 |
| env                    | Staging (*custom tag)                |
| http.method            | GET                                  |
| http.url               | http://{SERVER_ADDR}/style/{id}/make |
| http.status_code       | 502                                  |
| error                  | True                                 |
| django.resource.func   | make_shirts                          |
| django.resource.module | styling.views                        |

