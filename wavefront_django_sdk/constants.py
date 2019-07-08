"""
Constants for Django SDK.

@author: Hao Song (songhao@vmware.com)
"""

NULL_TAG_VAL = 'none'

REPORTER_PREFIX = 'django.'

WAVEFRONT_PROVIDED_SOURCE = 'wavefront-provided'

DJANGO_COMPONENT = 'django'

REQUEST_PREFIX = 'request'

RESPONSE_PREFIX = 'response'

HEART_BEAT_METRIC = "~component.heartbeat"

SOURCE_KEY = "source"

APPLICATION_TAG_KEY = "application"

CLUSTER_TAG_KEY = "cluster"

SHARD_TAG_KEY = "shard"

SERVICE_TAG_KEY = "service"

COMPONENT_TAG_KEY = "component"

HEART_BEAT_INTERVAL = 10
