import os
import glob
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from django.conf import settings
import libsbml
import roadrunner
import uuid
import json
import numpy as np
import logging
from django.http import JsonResponse, FileResponse, HttpResponse
from django.shortcuts import render
from django.views import View
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
import tempfile
from rest_framework.views import APIView
from django.core.exceptions import ValidationError
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import shutil
from rest_framework.response import Response
from rest_framework import status
import traceback



logger = logging.getLogger(__name__)


# Define model classes (Compartment, Species, Reaction, UnitDefinition, Parameter, Event)
class Compartment:
    def __init__(self, id, name, size):
        self.id = id
        self.name = name
        self.size = size

class Species:
    def __init__(self, id, name, metaid, substance_units, has_only_substance_units, initial_value, compartment, charge):
        self.id = id
        self.name = name
        self.metaid = metaid
        self.substance_units = substance_units
        self.has_only_substance_units = has_only_substance_units
        self.initial_value = initial_value
        self.compartment = compartment
        self.charge = charge

class Reaction:
    def __init__(self, id, name, metaid, reactants, products, modifiers, math):
        self.id = id
        self.name = name
        self.metaid = metaid
        self.reactants = reactants
        self.products = products
        self.modifiers = modifiers
        self.math = math
        self.reactants_products = f"Reactants: {self.reactants}<br>Products: {self.products}"

class UnitDefinition:
    def __init__(self, id, name, metaid, units):
        self.id = id
        self.name = name
        self.metaid = metaid
        self.units = units

class Parameter:
    def __init__(self, id, name, metaid, units, value):
        self.id = id
        self.name = name
        self.metaid = metaid
        self.units = units
        self.value = value

class Event:
    def __init__(self, id, name):
        self.id = id
        self.name = name

class ViewSBML(APIView):
    def get(self, request, format=None):
        try:
            sbml_files = self._find_sbml_files()
            if not sbml_files:
                return self._render_error(request, "No SBML files found in the directory.")

            temp_sbml_path = self._create_temp_file(request, sbml_files[0])
            request.session['temp_sbml_path'] = temp_sbml_path
            
            # Store original concentrations
            original_concentrations = self._get_initial_concentrations(temp_sbml_path)
            request.session['original_concentrations'] = original_concentrations

            model_data, errors = self._parse_sbml(temp_sbml_path)
            if errors:
                return self._render_error(request, errors)

            return render(request, 'view_sbml.html', {
                'model_data': model_data,
                'session_key': request.session.session_key
            })

        except Exception as e:
            logger.exception("Unexpected error in ViewSBML")
            return self._render_error(request, "An unexpected error occurred.") 

    def _get_initial_concentrations(self, sbml_file_path):
        reader = libsbml.SBMLReader()
        document = reader.readSBML(sbml_file_path)
        model = document.getModel()
        return {species.getId(): species.getInitialConcentration() for species in model.getListOfSpecies()}

    def _find_sbml_files(self):
        base_dir = settings.BASE_DIR
        return glob.glob(os.path.join(base_dir, '*.xml'))

    def _create_temp_file(self, request, original_file):
        temp_models_dir = os.path.join(settings.MEDIA_ROOT, 'temp_models')
        os.makedirs(temp_models_dir, exist_ok=True)

        temp_file_name = f'model_{request.session.session_key}.xml'
        temp_file_path = os.path.join(temp_models_dir, temp_file_name)

        shutil.copy2(original_file, temp_file_path)

        return temp_file_path

    def _parse_sbml(self, file_path):
        reader = libsbml.SBMLReader()
        document = reader.readSBML(file_path)
        
        if document.getNumErrors() > 0:
            errors = document.getErrorLog().toString()
            return None, errors
        
        model = document.getModel()
        
        if model is None:
            return None, "No model found in the SBML file."
        
        model_data = {
                'model_id': model.getId(),
                'model_name': model.getName(),
                'num_compartments': model.getNumCompartments(),
                'num_species': model.getNumSpecies(),
                'num_reactions': model.getNumReactions(),
                'num_parameters': model.getNumParameters(),
                'num_events': model.getNumEvents(),
                'compartments': [],
                'species': [],
                'reactions': [],
                'parameters': [],
                'events': [],
                'unit_definitions': [],
                'model_metadata': None
            }

        for i in range(model.getNumCompartments()):
            compartment = model.getCompartment(i)
            model_data['compartments'].append(Compartment(compartment.getId(), compartment.getName(), compartment.getSize()))

        for i in range(model.getNumSpecies()):
            species = model.getSpecies(i)
            model_data['species'].append(Species(
                species.getId(),
                species.getName(),
                species.getMetaId(),
                species.getSubstanceUnits(),
                species.getHasOnlySubstanceUnits(),
                species.getInitialAmount(),
                species.getCompartment(),
                species.getCharge()
            ))
        
        num_unit_definitions = model.getNumUnitDefinitions()
        for i in range(num_unit_definitions):
            unit_definition = model.getUnitDefinition(i)
            units = "; ".join([f"{libsbml.UnitKind_toString(unit.getKind())} ({unit.getExponent()})" for unit in unit_definition.getListOfUnits()])
            model_data['unit_definitions'].append(UnitDefinition(
                unit_definition.getId(),
                unit_definition.getName(),
                unit_definition.getMetaId(),
                units
            ))

        for i in range(model.getNumReactions()):
            reaction = model.getReaction(i)
            equation = libsbml.formulaToL3String(reaction.getKineticLaw().getMath())
            
            reactants = "; ".join([f"{reactant.getSpecies()} ({reactant.getStoichiometry()})" if reactant.isSetStoichiometry() else reactant.getSpecies() for reactant in reaction.getListOfReactants()])
            products = "; ".join([f"{product.getSpecies()} ({product.getStoichiometry()})" if product.isSetStoichiometry() else product.getSpecies() for product in reaction.getListOfProducts()])
            
            modifiers = "; ".join([modifier.getSpecies() for modifier in reaction.getListOfModifiers()])
            
            model_data['reactions'].append(Reaction(
                reaction.getId(),
                reaction.getName(),
                reaction.getMetaId(),
                reactants,
                products,
                modifiers,
                equation
        ))

        for i in range(model.getNumParameters()):
            parameter = model.getParameter(i)
            model_data['parameters'].append(Parameter(
                parameter.getId(),
                parameter.getName(),
                parameter.getMetaId(),  # Get metaid
                parameter.getUnits(),   # Get units
                parameter.getValue()
            ))

        for i in range(model.getNumEvents()):
            event = model.getEvent(i)
            model_data['events'].append(Event(event.getId(), event.getName()))

        # Extract model metadata
        model_metadata = ""
        if model.isSetNotes():
            model_metadata += "Notes:\n" + model.getNotesString() + "\n"
        if model.isSetAnnotation():
            model_metadata +=  model.getAnnotationString() + "\n"

        model_data['model_metadata'] = model_metadata
        errors = None
        return model_data, errors

    def _render_error(self, request, error_message):
        return render(
            request, 
            'error.html', 
            {'error_message': error_message}, 
            status=status.HTTP_400_BAD_REQUEST
        )

def add_brackets(name):
    return f"[{name}]" if not name.startswith('[') else name

def remove_brackets(name):
    return name.strip('[]')


import tellurium as te
import numpy as np

import tellurium as te
import numpy as np

import tellurium as te
import numpy as np
import roadrunner
import libsbml
import matplotlib.pyplot as plt

@method_decorator(csrf_exempt, name='dispatch')
class RunSimulation(APIView):
    def post(self, request, format=None):
        try:
            data = json.loads(request.body)
            execution_start = float(data.get('execution_start', 0))
            execution_end = float(data.get('execution_end', 30))
            execution_steps = int(data.get('execution_steps', 100))

            sbml_file_path = request.session.get('temp_sbml_path', '')
            if not sbml_file_path or not os.path.exists(sbml_file_path):
                return JsonResponse({'success': False, 'message': 'Temporary SBML file not found.'})

            # Load the model using tellurium
            r = te.loadSBMLModel(sbml_file_path)
            
            # Get all species in the model
            species = r.getFloatingSpeciesIds()

            # Get initial concentrations
            initial_concentrations = {s: r[s] for s in species}
            logger.info(f"Initial concentrations: {initial_concentrations}")

            # Run simulation
            result = r.simulate(execution_start, execution_end, execution_steps)

            # Extract concentrations of all species over time
            concentrations = result[:, 1:]  # Exclude the 'time' column

            # Calculate the median concentration for each node over the simulation period
            median_concentrations = np.median(concentrations, axis=0)

            # Create a dictionary of final (median) concentrations
            final_concentrations = dict(zip(species, median_concentrations))
            logger.info(f"Final concentrations: {final_concentrations}")

            # Update the SBML file with the final concentrations
            reader = libsbml.SBMLReader()
            document = reader.readSBML(sbml_file_path)
            model = document.getModel()

            for species_id, concentration in final_concentrations.items():
                species = model.getSpecies(species_id)
                if species:
                    species.setInitialConcentration(concentration)

            writer = libsbml.SBMLWriter()
            writer.writeSBMLToFile(document, sbml_file_path)

            # Update the session with the new concentrations
            request.session['original_concentrations'] = final_concentrations

            # Generate and save bar plot
            bar_plot_url = self._generate_bar_plot(list(final_concentrations.keys()), list(final_concentrations.values()))

            return JsonResponse({
                'success': True,
                'initial_concentrations': initial_concentrations,
                'final_concentrations': final_concentrations,
                'bar_plot_url': bar_plot_url
            })

        except Exception as e:
            logger.error(f"Error in RunSimulation: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return JsonResponse({
                'success': False,
                'message': f"An error occurred: {str(e)}",
                'traceback': traceback.format_exc()
            }, status=500)

    def _generate_bar_plot(self, species_names, concentrations):
        plt.figure(figsize=(12, 8))
        plt.bar(range(len(species_names)), concentrations, tick_label=species_names)
        plt.xlabel('Nodes (Species)')
        plt.ylabel('Concentration')
        plt.title('Concentrations of All Nodes')
        plt.xticks(rotation=90)  # Rotate x-axis labels for readability
        plt.tight_layout()
        plt.grid(axis='y')

        bar_plot_filename = f'bar_plot_{uuid.uuid4().hex}.png'
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
            plt.savefig(temp_file.name, dpi=300, bbox_inches='tight')
            plt.close()
            with open(temp_file.name, 'rb') as f:
                bar_plot_path = default_storage.save(bar_plot_filename, ContentFile(f.read()))
        os.unlink(temp_file.name)

        return default_storage.url(bar_plot_path)

# Endpoint to update parameters
class UpdateParameters(APIView):
    def post(self, request, format=None):
        try:
            data = json.loads(request.body)
            sbml_file = next((f for f in os.listdir(settings.BASE_DIR) if f.endswith('.xml')), None)
            if not sbml_file:
                return JsonResponse({'success': False, 'message': 'No SBML file found in the directory.'})

            sbml_file_path = os.path.join(settings.BASE_DIR, sbml_file)
            reader = libsbml.SBMLReader()
            document = reader.readSBML(sbml_file_path)

            if document.getNumErrors() > 0:
                errors = document.getErrorLog().toString()
                return JsonResponse({'success': False, 'message': errors})

            model = document.getModel()
            if model is None:
                return JsonResponse({'success': False, 'message': 'No model found in the SBML file.'})

            for parameter_id, new_value in data.items():
                parameter = model.getParameter(parameter_id)
                if parameter is not None:
                    parameter.setValue(float(new_value))

            writer = libsbml.SBMLWriter()
            writer.writeSBMLToFile(document, sbml_file_path)

            return JsonResponse({'success': True, 'message': 'Parameters updated successfully.'})
        except Exception as e:
            logger.error(f"Error in UpdateParameters: {str(e)}")
            return JsonResponse({'success': False, 'message': str(e)})

class DownloadSBMLView(View):
    def get(self, request, *args, **kwargs):
        try:
            file_name = 'autogenerated_model.xml'
            file_path = os.path.join(settings.BASE_DIR, file_name)
            
            if not os.path.exists(file_path):
                return HttpResponse(f"SBML file not found at {file_path}", status=404)
            
            if not os.access(file_path, os.R_OK):
                return HttpResponse(f"Permission denied: Cannot read SBML file at {file_path}", status=403)
            
            file_size = os.path.getsize(file_path)
            
            with open(file_path, 'rb') as file:
                response = FileResponse(file, content_type='application/xml')
                response['Content-Disposition'] = f'attachment; filename="{file_name}"'
                response['Content-Length'] = file_size
            
            return response
        
        except Exception as e:
            logger.exception("An error occurred while trying to download the SBML file")
            return HttpResponse(f"An error occurred: {str(e)}", status=500)

@method_decorator(csrf_exempt, name='dispatch')
class GetNodesView(View):
    def get(self, request):
        try:
            sbml_file_path = request.session.get('temp_sbml_path', '')
            if not sbml_file_path or not os.path.exists(sbml_file_path):
                return JsonResponse({'error': 'Temporary SBML file not found.'}, status=400)

            # Load the model using libSBML to get the most up-to-date values
            reader = libsbml.SBMLReader()
            document = reader.readSBML(sbml_file_path)
            model = document.getModel()
            
            original_concentrations = request.session.get('original_concentrations', {})
            
            nodes = []
            for species in model.getListOfSpecies():
                species_id = species.getId()
                nodes.append({
                    'id': species_id,
                    'name': species_id,
                    'clamped': species.getBoundaryCondition(),
                    'current_value': species.getInitialConcentration(),
                    'original_concentration': original_concentrations.get(species_id, species.getInitialConcentration())
                })
            
            return JsonResponse({'nodes': nodes})
        except Exception as e:
            logger.error(f"Error in GetNodesView: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return JsonResponse({'error': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class ClampNodesView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            clamped_nodes = data.get('clamped_nodes', [])

            sbml_file_path = request.session.get('temp_sbml_path', '')
            if not sbml_file_path or not os.path.exists(sbml_file_path):
                return JsonResponse({'success': False, 'message': 'Temporary SBML file not found.'})

            # Load the model using libSBML
            reader = libsbml.SBMLReader()
            document = reader.readSBML(sbml_file_path)
            model = document.getModel()

            for node in clamped_nodes:
                species_id = node['id']
                value = float(node['value'])
                species = model.getSpecies(species_id)
                if species:
                    species.setInitialConcentration(value)
                    species.setBoundaryCondition(True)

            # Save the updated SBML
            writer = libsbml.SBMLWriter()
            writer.writeSBMLToFile(document, sbml_file_path)

            return JsonResponse({'success': True})
        except Exception as e:
            logger.error(f"Error in ClampNodesView: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class CleanupTempFile(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            session_key = data.get('session_key')
            
            if session_key:
                temp_file_path = request.session.get('temp_sbml_path')
                if temp_file_path and os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
                    del request.session['temp_sbml_path']
                    return HttpResponse(status=200)
            
            return HttpResponse(status=400)
        except Exception as e:
            logger.error(f"Error in CleanupTempFile: {str(e)}")
            return HttpResponse(status=500)

class CheckModelState(APIView):
    def get(self, request, format=None):
        try:
            if 'rr_model_sbml' in request.session:
                rr = roadrunner.RoadRunner(request.session['rr_model_sbml'])
                species_ids = rr.model.getFloatingSpeciesIds()
                current_concentrations = {s: rr.getValue(s) for s in species_ids}
                return JsonResponse({
                    'success': True,
                    'current_concentrations': current_concentrations
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'No model state found in session'
                })
        except Exception as e:
            logger.error(f"Error in CheckModelState: {str(e)}")
            return JsonResponse({
                'success': False,
                'message': f"An error occurred: {str(e)}"
            }, status=500)