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

# Function to parse SBML file
def parse_sbml(sbml_file):
    reader = libsbml.SBMLReader()
    document = reader.readSBML(sbml_file)
    
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

    return model_data, None



# Endpoint to view SBML
class ViewSBML(APIView):
    def get(self, request, format=None):
        try:
            base_dir = settings.BASE_DIR
            sbml_files = glob.glob(os.path.join(base_dir, '*.xml'))

            if not sbml_files:
                return render(request, 'error.html', {'error_message': "No SBML files found in the directory."})

            sbml_file = sbml_files[0]
            model_data, errors = parse_sbml(sbml_file)

            if errors:
                return render(request, 'error.html', {'error_message': errors})

            return render(request, 'view_sbml.html', {'model_data': model_data})
        except Exception as e:
            logger.error(f"Error in ViewSBML: {str(e)}")
            return render(request, 'error.html', {'error_message': "An unexpected error occurred."})
# Endpoint to run simulation

def add_brackets(name):
    return f"[{name}]" if not name.startswith('[') else name

def remove_brackets(name):
    return name.strip('[]')

@method_decorator(csrf_exempt, name='dispatch')
class RunSimulation(APIView):
    def post(self, request, format=None):
        rr = None
        try:
            data = json.loads(request.body)
            execution_start = float(data.get('execution_start', 0))
            execution_end = float(data.get('execution_end', 100))
            execution_steps = int(data.get('execution_steps', 1000))
            clamped_species = data.get('clamped_species', [])

            logger.info(f"Simulation parameters: start={execution_start}, end={execution_end}, steps={execution_steps}, clamped={clamped_species}")

            sbml_file = next((f for f in os.listdir(settings.BASE_DIR) if f.endswith('.xml')), None)
            if not sbml_file:
                return JsonResponse({'success': False, 'message': 'No SBML file found in the project directory.'})
            
            sbml_file_path = os.path.join(settings.BASE_DIR, sbml_file)
            rr = roadrunner.RoadRunner(sbml_file_path)
            
            model = rr.getModel()
            if model is None:
                return JsonResponse({'success': False, 'message': 'Failed to get model from RoadRunner.'})

            all_species = model.getFloatingSpeciesIds()

            # Baseline simulation
            baseline_results = rr.simulate(execution_start, execution_end, execution_steps)
            baseline_data = {col: baseline_results[:, i].tolist() for i, col in enumerate(baseline_results.colnames)}

            rr.reset()
            
            # Clamp selected species
            for species in clamped_species:
                species_id = species['id']
                species_state = species['state']
                species_with_brackets = f"[{species_id}]" if not species_id.startswith('[') else species_id
                if species_with_brackets in all_species:
                    if species_state == 'activate':
                        rr.setValue(species_with_brackets, 1.0)
                    elif species_state == 'degenerate':
                        rr.setValue(species_with_brackets, 0.0)
                    rr.setBoundary(species_with_brackets, True)
                    logger.info(f"Clamped {species_with_brackets} to {1.0 if species_state == 'activate' else 0.0} and set as boundary species.")

            # Clamped simulation
            clamped_results = rr.simulate(execution_start, execution_end, execution_steps)
            clamped_data = {col: clamped_results[:, i].tolist() for i, col in enumerate(clamped_results.colnames)}

            # Generate plots
            plt.figure(figsize=(15, 10))
            for species in baseline_data.keys():
                if species != 'time':
                    plt.plot(baseline_data['time'], baseline_data[species], label=f'{species} (Baseline)')
                    plt.plot(clamped_data['time'], clamped_data[species], label=f'{species} (Clamped)', linestyle='--')
            plt.title('Baseline vs Clamped Simulation')
            plt.xlabel('Time')
            plt.ylabel('Concentration')
            plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='small')
            plt.grid(True)
            plt.tight_layout()

            # Save line plot
            line_plot_filename = f'line_plot_{uuid.uuid4().hex}.png'
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                plt.savefig(temp_file.name, dpi=300, bbox_inches='tight')
                plt.close()
                with open(temp_file.name, 'rb') as f:
                    line_plot_path = default_storage.save(line_plot_filename, ContentFile(f.read()))
            os.unlink(temp_file.name)

            # Create bar plot
            plt.figure(figsize=(15, 10))
            species = [s for s in baseline_data.keys() if s != 'time']
            baseline_final = [baseline_data[s][-1] for s in species]
            clamped_final = [clamped_data[s][-1] for s in species]
            x = np.arange(len(species))
            width = 0.35
            plt.bar(x - width/2, baseline_final, width, label='Baseline')
            plt.bar(x + width/2, clamped_final, width, label='Clamped')
            plt.xlabel('Species')
            plt.ylabel('Final Concentration')
            plt.title('Comparison of Final Values: Baseline vs Clamped')
            plt.xticks(x, species, rotation=90)
            plt.legend()
            plt.tight_layout()

            # Save bar plot
            bar_plot_filename = f'bar_plot_{uuid.uuid4().hex}.png'
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as temp_file:
                plt.savefig(temp_file.name, dpi=300, bbox_inches='tight')
                plt.close()
                with open(temp_file.name, 'rb') as f:
                    bar_plot_path = default_storage.save(bar_plot_filename, ContentFile(f.read()))
            os.unlink(temp_file.name)

            line_plot_url = default_storage.url(line_plot_path)
            bar_plot_url = default_storage.url(bar_plot_path)

            simulation_data = {
                'baseline': baseline_data,
                'clamped': clamped_data,
                'column_names': list(baseline_data.keys())
            }

            logger.info("Simulation completed successfully")
            return JsonResponse({
                'success': True,
                'simulation_data': simulation_data,
                'line_plot_url': line_plot_url,
                'bar_plot_url': bar_plot_url
            })

        except Exception as e:
            logger.error(f"Error in RunSimulation: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({'success': False, 'message': f"An error occurred: {str(e)}"}, status=500)
        finally:
            if rr is not None:
                del rr

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

import logging
logger = logging.getLogger(__name__)

class GetNodesView(View):
    def get(self, request):
        try:
            reader = libsbml.SBMLReader()
            sbml_file_path = os.path.join(settings.BASE_DIR, 'autogenerated_model.xml')
            document = reader.readSBML(sbml_file_path)
            model = document.getModel()
            
            nodes = []
            for species in model.getListOfSpecies():
                nodes.append({
                    'id': species.getId(),
                    'name': species.getName() or species.getId(),
                    'clamped': species.getConstant(),
                    'state': 'activate' if species.getConstant() else '',
                    'initial_concentration': species.getInitialConcentration()
                })
            
            return JsonResponse({'nodes': nodes})
        except Exception as e:
            logger.error(f"Error in GetNodesView: {str(e)}")
            return JsonResponse({'error': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class ClampNodesView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            clamped_nodes = data.get('clamped_nodes', [])

            reader = libsbml.SBMLReader()
            sbml_file_path = os.path.join(settings.BASE_DIR, 'autogenerated_model.xml')
            document = reader.readSBML(sbml_file_path)
            model = document.getModel()
            
            for species in model.getListOfSpecies():
                node_info = next((node for node in clamped_nodes if node['id'] == species.getId()), None)
                if node_info:
                    if node_info['state'] == 'activate':
                        species.setInitialConcentration(1.0)  # Set to high value for activation
                    elif node_info['state'] == 'degenerate':
                        species.setInitialConcentration(0.0)  # Set to low value for degeneration
                    species.setConstant(True)  # Set as boundary condition
                else:
                    # Unclamping: reset to original initial concentration and allow to vary
                    species.setConstant(False)
                    species.setInitialConcentration(species.getInitialConcentration())
            
            writer = libsbml.SBMLWriter()
            writer.writeSBML(document, sbml_file_path)

            return JsonResponse({'success': True})
        except Exception as e:
            logger.error(f"Error in ClampNodesView: {str(e)}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
