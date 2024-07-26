from django.http import JsonResponse
from django.shortcuts import render
from rest_framework.views import APIView
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
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sbml_files = glob.glob(os.path.join(base_dir, '*.xml'))

        if sbml_files:
            sbml_file = sbml_files[0]
        else:
            return render(request, 'error.html', {'error_message': "No SBML files found in the directory."})

        model_data, errors = parse_sbml(sbml_file)

        if errors:
            return render(request, 'error.html', {'error_message': errors})

        # Generate the reaction graph image
        network_data_file = os.path.join(base_dir, 'CRT.xlsx')  # Ensure this path is correct
        output_path = os.path.join(settings.MEDIA_ROOT, 'reaction_graph.png')
        reaction_graph_url = os.path.join(settings.MEDIA_URL, 'reaction_graph.png')

        return render(request, 'view_sbml.html', {'model_data': model_data} )
# Endpoint to run simulation

class RunSimulation(APIView):
    def post(self, request, format=None):
        try:
            # Parse the request body
            data = json.loads(request.body)
            execution_start = float(data.get('execution_start', 0))
            execution_end = float(data.get('execution_end', 100))
            execution_steps = int(data.get('execution_steps', 1000))

            sbml_file = next((f for f in os.listdir(settings.BASE_DIR) if f.endswith('.xml')), None)
            if not sbml_file:
                return JsonResponse({'success': False, 'message': 'No SBML file found in the project directory.'})
            sbml_file_path = os.path.join(settings.BASE_DIR, sbml_file)

            rr = roadrunner.RoadRunner(sbml_file_path)
            model = rr.getModel()
            il1beta_species = next((s for s in model.getFloatingSpeciesIds() if 'il' in s.lower() and '1' in s and 'beta' in s.lower()), None)
            if not il1beta_species:
                return JsonResponse({'success': False, 'message': 'IL-1β species not found in the model.'})

            # Use the execution parameters from the frontend
            baseline_results = rr.simulate(execution_start, execution_end, execution_steps)

            rr.reset()
            rr.setValue(il1beta_species, 1.0)
            rr.setValue(f'init({il1beta_species})', 1.0)
            rr.setBoundary(il1beta_species, True)
            stimulated_results = rr.simulate(execution_start, execution_end, execution_steps)

            fig, axs = plt.subplots(2, 2, figsize=(20, 20))
            fig.suptitle('Baseline and IL-1β Stimulation Results', fontsize=16)

            # Baseline Line Plot
            for column in baseline_results.colnames[1:]:
                axs[0, 0].plot(baseline_results['time'], baseline_results[column], label=column)
            axs[0, 0].set_title('Baseline Simulation')
            axs[0, 0].set_xlabel('Time')
            axs[0, 0].set_ylabel('Concentration')
            axs[0, 0].legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='xx-small')
            axs[0, 0].tick_params(axis='both', which='major', labelsize=8)
            axs[0, 0].grid(True)

            # Baseline Bar Plot
            last_values = [baseline_results[column][-1] for column in baseline_results.colnames[1:]]
            axs[0, 1].bar(baseline_results.colnames[1:], last_values)
            axs[0, 1].set_title('Baseline Final Values')
            axs[0, 1].set_xlabel('Species')
            axs[0, 1].set_ylabel('Concentration')
            axs[0, 1].tick_params(axis='x', rotation=90, labelsize=8)
            axs[0, 1].tick_params(axis='y', labelsize=8)

            # Stimulated Line Plot
            for column in stimulated_results.colnames[1:]:
                axs[1, 0].plot(stimulated_results['time'], stimulated_results[column], label=column)
            axs[1, 0].set_title('IL-1β Stimulated Simulation')
            axs[1, 0].set_xlabel('Time')
            axs[1, 0].set_ylabel('Concentration')
            axs[1, 0].legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize='xx-small')
            axs[1, 0].tick_params(axis='both', which='major', labelsize=8)
            axs[1, 0].grid(True)

            # Stimulated Bar Plot
            last_values = [stimulated_results[column][-1] for column in stimulated_results.colnames[1:]]
            axs[1, 1].bar(stimulated_results.colnames[1:], last_values)
            axs[1, 1].set_title('IL-1β Stimulated Final Values')
            axs[1, 1].set_xlabel('Species')
            axs[1, 1].set_ylabel('Concentration')
            axs[1, 1].tick_params(axis='x', rotation=90, labelsize=8)
            axs[1, 1].tick_params(axis='y', labelsize=8)

            plt.tight_layout()

            plot_filename = f'simulation_plot_{uuid.uuid4().hex}.png'
            plot_path = os.path.join(settings.MEDIA_ROOT, plot_filename)
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            plt.close()

            plot_url = os.path.join(settings.MEDIA_URL, plot_filename)

            def named_array_to_dict(named_array):
                return {
                    'time': named_array['time'].tolist(),
                    'species': {col: named_array[col].tolist() for col in named_array.colnames if col != 'time'}
                }

            simulation_data = {
                'baseline': named_array_to_dict(baseline_results),
                'stimulated': named_array_to_dict(stimulated_results),
                'column_names': baseline_results.colnames
            }

            return JsonResponse({
                'success': True,
                'simulation_data': simulation_data,
                'plot_url': plot_url
            })

        except Exception as e:
            import traceback
            print(traceback.format_exc())  # This will print the full traceback
            return JsonResponse({'success': False, 'message': str(e)})

# Endpoint to update parameters
class UpdateParameters(APIView):
    def post(self, request, format=None):
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sbml_files = glob.glob(os.path.join(base_dir, '*.xml'))

            if not sbml_files:
                return JsonResponse({'success': False, 'message': 'No SBML files found in the directory.'})

            sbml_file = sbml_files[0]

            reader = libsbml.SBMLReader()
            document = reader.readSBML(sbml_file)

            if document.getNumErrors() > 0:
                errors = document.getErrorLog().toString()
                return JsonResponse({'success': False, 'message': errors})

            model = document.getModel()

            if model is None:
                return JsonResponse({'success': False, 'message': 'No model found in the SBML file.'})

            for i in range(model.getNumParameters()):
                parameter_id = model.getParameter(i).getId()
                new_value_str = request.POST.get(parameter_id)
                if new_value_str is not None:
                    new_value = float(new_value_str)
                    model.getParameter(i).setValue(new_value)

            writer = libsbml.SBMLWriter()
            writer.writeSBMLToFile(document, sbml_file)

            return JsonResponse({'success': True, 'message': 'Parameters updated successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

