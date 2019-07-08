"""
Tracing Context Injection.

@author: Hao Song (songhao@vmware.com)
"""
import opentracing

import six


# pylint: disable=protected-access
def inject_as_headers(tracer, span, request):
    """Inject tracing context into header."""
    text_carrier = {}
    tracer._tracer.inject(span.context, opentracing.Format.TEXT_MAP,
                          text_carrier)
    for key, val in six.iteritems(text_carrier):
        request.add_header(key, val)
