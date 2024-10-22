// main.js

document.addEventListener('DOMContentLoaded', function() {
    // Initialize all event listeners
    initializeEventListeners();
    initializeTooltips();
});

function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });
}

function initializeEventListeners() {
    // Node Tray Button
    const nodeTrayButton = document.getElementById("node_tray_button");
    if (nodeTrayButton) {
        nodeTrayButton.addEventListener("click", function() {
            console.log("Node Tray button clicked");
            fetchNodesAndPopulateModal();
        });
    }

    // Run Simulation Button
    const simulateButton = document.getElementById("simulate_button");
    if (simulateButton) {
        simulateButton.addEventListener("click", function() {
            console.log("Run Simulation button clicked");
            runSimulation();
        });
    }

    // Update Parameters Form
    const updateParametersForm = document.getElementById("update_parameters_form");
    if (updateParametersForm) {
        updateParametersForm.addEventListener("submit", function(event) {
            event.preventDefault();
            console.log("Update Parameters form submitted");
            alert("Updating");
            handleParameterUpdate();
            
        });
    }
}

function fetchNodesAndPopulateModal() {
    fetch("/network-model/get_nodes/")
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log("Nodes data received:", data);
            populateNodeModal(data.nodes);
        })
        .catch(error => {
            console.error("Error fetching nodes:", error);
            alert("Error fetching nodes: " + error.message);
        });
}

function populateNodeModal(nodes) {
    const nodeTrayBody = document.getElementById("nodeTrayBody");
    if (!nodeTrayBody) return;

    // Clear existing content
    nodeTrayBody.innerHTML = "";

    // Add each node row
    nodes.forEach(node => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${node.name}</td>
            <td>
                <div class="form-check">
                    <input class="form-check-input node-checkbox" 
                           type="checkbox" 
                           value="${node.id}" 
                           id="clamp_${node.id}" 
                           ${node.clamped ? 'checked' : ''}>
                    <label class="form-check-label" for="clamp_${node.id}">Clamp</label>
                </div>
            </td>
            <td>
                <input type="number" 
                       step="any" 
                       class="form-control form-control-sm node-value" 
                       id="value_${node.id}" 
                       value="${node.current_value}" 
                       ${!node.clamped ? 'disabled' : ''}>
            </td>
            <td>${node.original_concentration}</td>
        `;
        nodeTrayBody.appendChild(row);
    });

    // Add checkbox event listeners
    document.querySelectorAll('.node-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const valueInput = this.closest('tr').querySelector('.node-value');
            valueInput.disabled = !this.checked;
            if (this.checked && !valueInput.value) {
                valueInput.value = "1";
            }
        });
    });

    // Add save button event listener
    const saveButton = document.getElementById("saveNodeTray");
    if (saveButton) {
        saveButton.addEventListener("click", saveClampedNodes);
    }

    // Show the modal
    const modal = new bootstrap.Modal(document.getElementById('nodeTrayModal'));
    modal.show();
}

function saveClampedNodes() {
    const clampedNodes = [];
    document.querySelectorAll("#nodeTrayBody tr").forEach(row => {
        const checkbox = row.querySelector('.node-checkbox');
        const valueInput = row.querySelector('.node-value');
        if (checkbox && checkbox.checked) {
            clampedNodes.push({
                id: checkbox.value,
                value: parseFloat(valueInput.value) || 1
            });
        }
    });

    fetch("/network-model/clamp_nodes/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value
        },
        body: JSON.stringify({ clamped_nodes: clampedNodes })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert("Node clamping updated successfully!");
            const modal = bootstrap.Modal.getInstance(document.getElementById('nodeTrayModal'));
            if (modal) modal.hide();
        } else {
            alert("Error updating node clamping: " + (data.error || "Unknown error"));
        }
    })
    .catch(error => {
        console.error("Error:", error);
        alert("Error updating node clamping: " + error.message);
    });
}

function handleParameterUpdate() {
    const parameters = {};
    document.querySelectorAll('[id^="parameter_"]').forEach(input => {
        const parameterId = input.id.replace('parameter_', '');
        parameters[parameterId] = parseFloat(input.value);
    });

    fetch("/network-model/update_parameters/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value
        },
        body: JSON.stringify(parameters)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert("Parameters updated successfully!");
        } else {
            alert("Error updating parameters: " + data.message);
        }
    })
    .catch(error => {
        console.error("Error:", error);
        alert("Error updating parameters: " + error.message);
    });
}

function runSimulation() {
    const loader = document.getElementById("loader");
    if (loader) loader.style.display = "flex";

    const executionStart = parseFloat(document.getElementById("execution_start").value) || 0;
    const executionEnd = parseFloat(document.getElementById("execution_end").value) || 30;
    const executionSteps = parseInt(document.getElementById("execution_steps").value) || 100;

    fetch("/network-model/run_simulation/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": document.querySelector('[name=csrfmiddlewaretoken]').value
        },
        body: JSON.stringify({
            execution_start: executionStart,
            execution_end: executionEnd,
            execution_steps: executionSteps
        })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(errorData => {
                throw new Error(`HTTP error! status: ${response.status}, message: ${errorData.message}, traceback: ${errorData.traceback}`);
            });
        }
        return response.json();
    })
    .then(data => {
        if (loader) loader.style.display = "none";

        if (!data.success) {
            throw new Error(data.message || "Simulation failed");
        }

        // Update plot
        const plotContainer = document.getElementById("plot-container");
        if (plotContainer) {
            plotContainer.innerHTML = `<img src="${data.bar_plot_url}" alt="Bar Plot" style="max-width: 100%; height: auto;">`;
        }

        // Update results table
        const resultsContainer = document.getElementById("results-container");
        if (resultsContainer) {
            let resultsHtml = "<h3>Simulation Results</h3><table><tr><th>Species</th><th>Initial Concentration</th><th>Final Concentration</th></tr>";
            
            // Get unique set of all species from both concentrations
            const allSpecies = Array.from(new Set([
                ...Object.keys(data.initial_concentrations || {}),
                ...Object.keys(data.final_concentrations || {})
            ])).sort();

            allSpecies.forEach(species => {
                const initialValue = (data.initial_concentrations && data.initial_concentrations[species]) || 0;
                const finalValue = (data.final_concentrations && data.final_concentrations[species]) || 0;
                
                resultsHtml += `<tr>
                    <td>${species}</td>
                    <td>${Number(initialValue).toFixed(6)}</td>
                    <td>${Number(finalValue).toFixed(6)}</td>
                </tr>`;
            });
            
            resultsHtml += "</table>";
            resultsContainer.innerHTML = resultsHtml;
        }

        // Show results modal
        const simulationModal = new bootstrap.Modal(document.getElementById('simulation-modal'));
        if (simulationModal) {
            simulationModal.show();
        }
    })
    .catch(error => {
        console.error("Error in simulation:", error);
        if (loader) loader.style.display = "none";
        alert("An error occurred while running the simulation: " + error.message);
    });
}

function updatePlot(plotUrl) {
    const plotContainer = document.getElementById("plot-container");
    if (plotContainer) {
        plotContainer.innerHTML = `<img src="${plotUrl}" alt="Bar Plot" style="max-width: 100%; height: auto;">`;
    }
}

function updateResults(data) {
    const resultsContainer = document.getElementById("results-container");
    if (!resultsContainer) return;

    const allSpecies = new Set([
        ...Object.keys(data.initial_concentrations || {}),
        ...Object.keys(data.final_concentrations || {})
    ]);

    let resultsHtml = `
        <h3>Simulation Results</h3>
        <table>
            <tr>
                <th>Species</th>
                <th>Initial Concentration</th>
                <th>Final Concentration</th>
            </tr>
    `;

    allSpecies.forEach(species => {
        const initial = data.initial_concentrations?.[species] || 0;
        const final = data.final_concentrations?.[species] || 0;
        
        resultsHtml += `
            <tr>
                <td>${species}</td>
                <td>${Number(initial).toFixed(6)}</td>
                <td>${Number(final).toFixed(6)}</td>
            </tr>
        `;
    });

    resultsHtml += "</table>";
    resultsContainer.innerHTML = resultsHtml;
}

// Cleanup on page unload
window.addEventListener('beforeunload', function(e) {
    e.preventDefault();
    e.returnValue = '';

    const sessionKey = document.getElementById('session-key')?.value;
    if (sessionKey) {
        navigator.sendBeacon('/network-model/cleanup-temp-file/', 
            JSON.stringify({ session_key: sessionKey })
        );
    }
});