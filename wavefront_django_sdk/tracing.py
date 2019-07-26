"""
Wavefront Django Tracing.

@author: Hao Song (songhao@vmware.com)
"""

from django.urls import resolve

from django_opentracing import tracing

from .constants import DJANGO_COMPONENT


class DjangoTracing(tracing.DjangoTracing):
    """Wavefront Django Tracing."""

    def _finish_tracing(self, request, response=None, error=None):
        scope = self._current_scopes.pop(request, None)
        if scope is None:
            return
        if response is not None:
            func_name = resolve(request.path_info).func.__name__
            module_name = resolve(request.path_info).func.__module__
            scope.span.set_tag("http.status_code", str(response.status_code))
            if 400 <= response.status_code <= 599:
                scope.span.set_tag("error", "true")
                error_log = {"error_code": response.status_code}
                scope.span.log_kv(error_log)
            scope.span.set_tag("span.kind", "server")
            scope.span.set_tag("django.resource.module", module_name)
            scope.span.set_tag("django.resource.func", func_name)
            scope.span.set_tag("component", DJANGO_COMPONENT)
            scope.span.set_tag("http.method", request.method)
            scope.span.set_tag("http.url", request.build_absolute_uri())
        scope.close()
