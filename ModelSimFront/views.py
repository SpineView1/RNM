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
import tellurium as te

logger = logging.getLogger(__name__)

# Add at the top of your file
FIXED_ORDER = [
    'ACAN', 'COL2A', 'COL1A', 'COL10A1', 'TNF', 'IL_12A', 'IL_17A', 
    'IL_1alpha', 'IL_1beta', 'IL_4', 'IL_6', 'IL_8', 'IL_10', 'TGF_beta', 
    'IGF1', 'CCL22', 'GDF5', 'PGRN', 'CCL', 'MMP1', 'MMP2', 'MMP3', 'MMP9', 
    'MMP13', 'VEGF', 'ADAMTS4_5', 'TIMP1_2', 'TIMP3'
]


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

            # Reset clamped nodes for new session
            request.session['clamped_nodes'] = {}

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
            notes_string = model.getNotesString()
            # Remove XML/XHTML tags and unescape HTML entities
            import re
            from html import unescape
            
            # Remove the notes tags
            notes_string = re.sub(r'<\/?notes>', '', notes_string)
            # Remove the xmlns attribute
            notes_string = re.sub(r'\sxmlns="[^"]+"', '', notes_string)
            # Remove body tags
            notes_string = re.sub(r'<\/?body>', '', notes_string)
            
            model_metadata = unescape(notes_string).strip()

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

@method_decorator(csrf_exempt, name='dispatch')
class RunSimulation(APIView):
    def get_baseline_values(self):
        return {
            'ACAN': 0.9983613865848022,
            'ADAMTS4_5': 8.092625378922021e-05,
            'CCL': 2.5173856294816446e-08,
            'CCL22': 0.17738609790383056,
            'CCN2': 0.9999999692100777,
            'COL10A1': 3.0059609346285684e-10,
            'COL1A': 2.0001357420127274e-09,
            'COL2A': 0.9983410707055728,
            'CSF2': 3.005448970436891e-10,
            'GDF5': 0.9999999979997497,
            'IFN_gamma': 7.284689827839055e-11,
            'IGF1': 0.9957857113761,
            'IL_10': 0.7387459489158427,
            'IL_12A': 5.954032557892407e-09,
            'IL_17A': 2.6567000452589797e-07,
            'IL_18': 1.2429956788066651e-10,
            'IL_1RA': 2.0001906623784544e-09,
            'IL_1alpha': 1.2421322758498211e-10,
            'IL_1beta': 1.4836375074985397e-08,
            'IL_4': 0.9298957607389551,
            'IL_6': 0.0086618406386164,
            'TNF': 0.0786618406386164,
            'IL_8': 0.00012028793176261721,
            'MMP1': 2.5182956776717087e-09,
            'MMP13': 4.342611601799085e-05,
            'MMP2': 3.5488844978246427e-05,
            'MMP3': 1.1897600726024104e-05,
            'MMP9': 1.92924087560209e-12,
            'PGRN': 4.0848997437474845e-14,
            'TGF_beta': 0.9999990861413531,
            'TIMP1_2': 0.9912141863372799,
            'TIMP3': 0.9999999334058873,
            'VEGF': 2.3190753403830494e-11
        }

    def post(self, request, format=None):
        try:
            data = json.loads(request.body)
            execution_start = 0
            execution_end = 30
            execution_steps = 100

            sbml_file_path = request.session.get('temp_sbml_path', '')
            if not sbml_file_path or not os.path.exists(sbml_file_path):
                return JsonResponse({'success': False, 'message': 'Temporary SBML file not found.'})

            # Load model
            r = te.loadSBMLModel(sbml_file_path)
            
            # Initialize with baseline values if no last state
            if 'last_state' not in request.session:
                request.session['last_state'] = self.get_baseline_values()

            # Set initial conditions from last state
            last_state = request.session['last_state']
            for species, value in last_state.items():
                try:
                    r[species] = value
                except Exception as e:
                    logger.error(f"Error setting {species}: {str(e)}")
                    continue

            # Get clamped nodes
            clamped_nodes = request.session.get('clamped_nodes', {})
            
            # Run simulation with proper clamping
            result = []
            time_points = np.linspace(execution_start, execution_end, execution_steps)
            
            for t in np.diff(time_points):
                # Apply clamps at each step
                for species_id, value in clamped_nodes.items():
                    try:
                        r[species_id] = value
                    except Exception as e:
                        logger.error(f"Error clamping {species_id}: {str(e)}")
                        continue
                
                # Simulate one step
                r.simulate(0, t, 2)
                state = r.getFloatingSpeciesConcentrations()
                result.append(state)
            
            result = np.array(result)
            species_names = r.getFloatingSpeciesIds()
            
            # Get final state
            final_state = {
                species_id: result[-1][i]
                for i, species_id in enumerate(species_names)
            }
            
            # Update session state
            request.session['last_state'] = final_state
            
            # Generate plot using fixed order
            plot_species = [s for s in FIXED_ORDER if s in final_state]
            concentrations = [final_state[s] for s in plot_species]
            
            bar_plot_url = self._generate_bar_plot(plot_species, concentrations)

            return JsonResponse({
                'success': True,
                'initial_concentrations': last_state,
                'final_concentrations': final_state,
                'bar_plot_url': bar_plot_url
            })

        except Exception as e:
            logger.error(f"Error in RunSimulation: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return JsonResponse({
                'success': False, 
                'message': str(e),
                'traceback': traceback.format_exc()
            }, status=500)

    def _generate_bar_plot(self, species_names, concentrations):
        plt.figure(figsize=(15, 8))
        
        x = np.arange(len(species_names))
        width = 0.35
        
        # Create bar colors based on clamped nodes
        bar_colors = ['skyblue'] * len(species_names)
        clamped_nodes = self.request.session.get('clamped_nodes', {})
        for i, species_id in enumerate(species_names):
            if species_id in clamped_nodes:
                bar_colors[i] = 'yellow'
        
        plt.bar(x, concentrations, tick_label=species_names, color=bar_colors)
        plt.xticks(rotation=45, ha='right')
        plt.ylabel('Concentration')
        plt.title('Concentrations of All Nodes')
        plt.grid(True, axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()

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
            
            sbml_file_path = request.session.get('temp_sbml_path', '')
            if not sbml_file_path or not os.path.exists(sbml_file_path):
                return JsonResponse({'success': False, 'message': 'Temporary SBML file not found.'})

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
            # Get the temporary SBML file path from the session
            sbml_file_path = request.session.get('temp_sbml_path', '')
            if not sbml_file_path or not os.path.exists(sbml_file_path):
                # If temp file not found, try the default path
                file_name = 'autogenerated_model.xml'
                sbml_file_path = os.path.join(settings.BASE_DIR, file_name)

            if not os.path.exists(sbml_file_path):
                return HttpResponse(f"SBML file not found at {sbml_file_path}", status=404)
            
            if not os.access(sbml_file_path, os.R_OK):
                return HttpResponse(f"Permission denied: Cannot read SBML file at {sbml_file_path}", status=403)

            # Create response with file
            file_obj = open(sbml_file_path, 'rb')
            response = FileResponse(
                file_obj,
                content_type='application/xml',
                as_attachment=True,
                filename='network_model.xml'
            )
            
            # Let FileResponse handle closing the file
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
            clamped_nodes = request.session.get('clamped_nodes', {})
            
            nodes = []
            for species in model.getListOfSpecies():
                species_id = species.getId()
                nodes.append({
                    'id': species_id,
                    'name': species_id,
                    'clamped': species_id in clamped_nodes,
                    'current_value': clamped_nodes.get(species_id, species.getInitialConcentration()),
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

            # Use libSBML to modify the model
            reader = libsbml.SBMLReader()
            document = reader.readSBML(sbml_file_path)
            model = document.getModel()

            # First, reset all species to not be boundary conditions
            for species in model.getListOfSpecies():
                species.setBoundaryCondition(False)
                species.setConstant(False)

            # Set clamped nodes
            clamped_dict = {}
            for node in clamped_nodes:
                species_id = node['id']
                value = float(node['value'])
                
                species = model.getSpecies(species_id)
                if species:
                    species.setBoundaryCondition(True)
                    species.setConstant(True)
                    species.setInitialConcentration(value)
                    clamped_dict[species_id] = value

            # Save the modified SBML file
            writer = libsbml.SBMLWriter()
            writer.writeSBMLToFile(document, sbml_file_path)

            # Update the session
            request.session['clamped_nodes'] = clamped_dict
            
            # If this is the first clamp after baseline, store baseline state
            if 'baseline_state' not in request.session:
                # Load model to get baseline state
                r = te.loadSBMLModel(sbml_file_path)
                baseline_state = {s: r[s] for s in r.getFloatingSpeciesIds()}
                request.session['baseline_state'] = baseline_state

            return JsonResponse({'success': True})

        except Exception as e:
            logger.error(f"Error in ClampNodesView: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return JsonResponse({
                'success': False, 
                'error': str(e),
                'traceback': traceback.format_exc()
            }, status=500)

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