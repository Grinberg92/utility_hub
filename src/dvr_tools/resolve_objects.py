import DaVinciResolveScript as dvr
class ResolveObjects:
    """
    Класс получает основные объекты резолв.

    """
    def __init__(self):
        self.resolve = dvr.scriptapp("Resolve")
        self.resolve_project_manager = self.resolve.GetProjectManager()
        self.resolve_project = self.resolve_project_manager.GetCurrentProject()
        self.resolve_mediapool = self.resolve_project.GetMediaPool()
        self.resolve_timeline = self.resolve_project.GetCurrentTimeline()

    @property
    def timeline(self):
        return self.resolve_timeline
    
    @property
    def mediapool(self):
        return self.resolve_mediapool
    
    @property
    def project(self):
        return self.resolve_project
    
    @property
    def project_manager(self):
        return self.resolve_project_manager

    
if __name__ == "__main":
    ResolveObjects()




