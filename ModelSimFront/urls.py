from django.urls import path
from .views import RunSimulation, ViewSBML, UpdateParameters, DownloadSBMLView, GetNodesView, ClampNodesView

urlpatterns = [
    path('', ViewSBML.as_view(), name='view_sbml'),
    path('update_parameters/', UpdateParameters.as_view(), name='update_parameters'), 
    path('run_simulation/', RunSimulation.as_view(), name='run_simulation'),
    path('download-sbml/', DownloadSBMLView.as_view(), name='download_sbml'),
    path('get_nodes/', GetNodesView.as_view(), name='get_nodes'),
    path('clamp_nodes/', ClampNodesView.as_view(), name='clamp_nodes'),


]
