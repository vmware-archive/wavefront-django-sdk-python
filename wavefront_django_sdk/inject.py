import six
import opentracing


def inject_as_headers(tracer, span, request):
    text_carrier = {}
    tracer._tracer.inject(span.context, opentracing.Format.TEXT_MAP,
                          text_carrier)
    for k, v in six.iteritems(text_carrier):
        request.add_header(k, v)
