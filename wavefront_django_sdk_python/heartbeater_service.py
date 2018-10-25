import time
import logging
from threading import Timer
from wavefront_django_sdk_python.constants import HEART_BEAT_METRIC, \
    APPLICATION_TAG_KEY, CLUSTER_TAG_KEY, SERVICE_TAG_KEY, SHARD_TAG_KEY, \
    COMPONENT_TAG_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HeartbeaterService:
    def __init__(self, wavefront_client, application_tags, component, source,
                 reporting_interval_seconds):
        self.wavefront_client = wavefront_client
        self.application_tags = application_tags
        self.source = source
        self.reporting_interval_seconds = reporting_interval_seconds
        self.heartbeat_metric_tags = {
            APPLICATION_TAG_KEY: application_tags.application,
            CLUSTER_TAG_KEY: application_tags.cluster,
            SERVICE_TAG_KEY: application_tags.service,
            SHARD_TAG_KEY: application_tags.shard,
            COMPONENT_TAG_KEY: component
        }
        self._timer = None
        self._schedule_timer()

    def _schedule_timer(self):
        self._timer = Timer(self.reporting_interval_seconds, self._run)
        self._timer.start()

    def _run(self):
        try:
            self._report()
        finally:
            self._schedule_timer()

    def _report(self):
        self.wavefront_client.send_metric(HEART_BEAT_METRIC, 1.0,
                                          time.time(), self.source,
                                          self.heartbeat_metric_tags)
