class ApplicationTags:

    def __init__(self, application, service, cluster=None, shard=None,
                 custom_tags=None):
        if not application:
            raise AttributeError('Missing "application" parameter in '
                                 'ApplicationTags!')
        if not service:
            raise AttributeError('Missing "service" parameter in '
                                 'ApplicationTags!')
        self._application = application
        self._service = service
        self._cluster = cluster
        self._shard = shard
        self._custom_tags = custom_tags

    @property
    def application(self):
        return self._application

    @property
    def service(self):
        return self._service

    @property
    def cluster(self):
        return self._cluster

    @property
    def shard(self):
        return self._shard

    @property
    def custom_tags(self):
        return self._custom_tags
