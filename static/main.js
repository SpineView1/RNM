document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap components
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    })

    // Initialize Bootstrap tabs
    var tabElms = document.querySelectorAll('button[data-bs-toggle="tab"]')
    tabElms.forEach(function(tabElm) {
        new bootstrap.Tab(tabElm)
    })

    // Event listener for the Node Tray button
    var nodeTrayButton = document.getElementById("node_tray_button");
    if (nodeTrayButton) {
        nodeTrayButton.addEventListener("click", function() {
            console.log("Node Tray button clicked");
            fetchNodesAndPopulateModal();
        });
    } else {
        console.error("Node Tray button not found");
    }

    // Event listener for the "Run Simulation" button
    var simulateButton = document.getElementById("simulate_button");
    if (simulateButton) {
        simulateButton.addEventListener("click", function() {
            console.log("Run Simulation button clicked");
            runSimulation();
        });
    } else {
        console.error("Simulate button not found");
    }

    // Event listener for the "Update Parameters" form
    var updateParametersForm = document.getElementById("update_parameters_form");
    if (updateParametersForm) {
        updateParametersForm.addEventListener("submit", function(event) {
            event.preventDefault();
            console.log("Update Parameters form submitted");
            updateParameters();
        });
    } else {
        console.error("Update Parameters form not found");
    }

    // Attach the event listener to the save button
    var saveNodeTrayButton = document.getElementById("saveNodeTray");
    if (saveNodeTrayButton) {
        saveNodeTrayButton.addEventListener("click", saveClampedNodes);
    } else {
        console.error("Save Node Tray button not found");
    }
});

function showLoader() {
    const loader = document.getElementById("loader");
    if (loader) {
        loader.style.display = "flex";
    } else {
        console.error("Loader element not found");
    }
}

function hideLoader() {
    const loader = document.getElementById("loader");
    if (loader) {
        loader.style.display = "none";
    } else {
        console.error("Loader element not found");
    }
}

function fetchNodesAndPopulateModal() {
    console.log("Fetching nodes...");
    showLoader();
    fetch("/network-model/get_nodes/")
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log("Nodes data received:", data);
            const nodeTrayBody = document.getElementById("nodeTrayBody");
            nodeTrayBody.innerHTML = "";  // Clear existing content

            data.nodes.forEach(node => {
                const row = document.createElement("tr");
                row.innerHTML = `
                    <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${node.name}</td>
                    <td>
                        <div class="form-check">
                            <input class="form-check-input node-checkbox" type="checkbox" value="${node.id}" id="clamp_${node.id}" ${node.clamped ? 'checked' : ''}>
                            <label class="form-check-label" for="clamp_${node.id}">
                                Clamp
                            </label>
                        </div>
                    </td>
                    <td>
                        <select class="form-select form-select-sm node-state-toggle" id="state_${node.id}" ${!node.clamped ? 'disabled' : ''}>
                            <option value="activate" ${node.state === 'activate' ? 'selected' : ''}>Activate</option>
                            <option value="degenerate" ${node.state === 'degenerate' ? 'selected' : ''}>Degenerate</option>
                        </select>
                    </td>
                    <td style="max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                        ${node.initial_concentration}
                    </td>
                `;
                nodeTrayBody.appendChild(row);
            });

            // Add event listeners to checkboxes
            document.querySelectorAll('.node-checkbox').forEach(checkbox => {
                checkbox.addEventListener('change', function() {
                    const stateSelect = this.closest('tr').querySelector('.node-state-toggle');
                    stateSelect.disabled = !this.checked;
                    if (this.checked && !stateSelect.value) {
                        stateSelect.value = 'activate'; // Default to 'activate' when clamped
                    }
                });
            });

            // Show the modal
            var nodeTrayModal = new bootstrap.Modal(document.getElementById('nodeTrayModal'));
            nodeTrayModal.show();
            hideLoader();
        })
        .catch(error => {
            console.error("Error fetching nodes:", error);
            alert("An error occurred while fetching nodes. Check the console for details.");
            hideLoader();
        });
}

function saveClampedNodes() {
    showLoader();
    const clampedNodes = [];
    document.querySelectorAll("#nodeTrayBody tr").forEach(row => {
        const checkbox = row.querySelector('input[type="checkbox"]');
        const stateSelect = row.querySelector('select');
        if (checkbox.checked) {
            clampedNodes.push({
                id: checkbox.value,
                state: stateSelect.value
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
        hideLoader();
        if (data.success) {
            alert("Node clamping updated successfully!");
            bootstrap.Modal.getInstance(document.getElementById('nodeTrayModal')).hide();
        } else {
            alert("Error updating node clamping: " + (data.error || "Unknown error"));
        }
    })
    .catch(error => {
        console.error("Error:", error);
        alert("An error occurred while updating node clamping.");
        hideLoader();
    });
}

function runSimulation() {
    console.log("runSimulation function called");
    showLoader();

    var csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    console.log("CSRF token retrieved:", csrftoken);

    var executionStart = parseFloat(document.getElementById("execution_start").value) || 0;
    var executionEnd = parseFloat(document.getElementById("execution_end").value) || 100;
    var executionSteps = parseInt(document.getElementById("execution_steps").value) || 1000;
    console.log("Execution parameters:", { start: executionStart, end: executionEnd, steps: executionSteps });

    // Get clamped nodes
    var clampedNodes = [];
    document.querySelectorAll("#nodeTrayBody tr").forEach(row => {
        const checkbox = row.querySelector('input[type="checkbox"]');
        const stateSelect = row.querySelector('select');
        if (checkbox && checkbox.checked) {
            clampedNodes.push({
                id: checkbox.value,
                state: stateSelect ? stateSelect.value : 'activate'
            });
        }
    });
    console.log("Clamped nodes:", clampedNodes);

    fetch("/network-model/run_simulation/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrftoken
        },
        body: JSON.stringify({
            execution_start: executionStart,
            execution_end: executionEnd,
            execution_steps: executionSteps,
            clamped_species: clampedNodes
        })
    })
    .then(response => {
        console.log("Received response:", response);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        console.log("Received data:", data);
        hideLoader();

        if (data.success) {
            var plotContainer = document.getElementById("plot-container");
            if (plotContainer) {
                plotContainer.innerHTML = `
                    <ul class="nav nav-tabs" id="plotTabs" role="tablist">
                        <li class="nav-item" role="presentation">
                            <button class="nav-link active" id="line-plot-tab" data-bs-toggle="tab" data-bs-target="#line-plot" type="button" role="tab" aria-controls="line-plot" aria-selected="true">Line Plot</button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" id="bar-plot-tab" data-bs-toggle="tab" data-bs-target="#bar-plot" type="button" role="tab" aria-controls="bar-plot" aria-selected="false">Bar Plot</button>
                        </li>
                    </ul>
                    <div class="tab-content" id="plotTabsContent">
                        <div class="tab-pane fade show active" id="line-plot" role="tabpanel" aria-labelledby="line-plot-tab">
                            <img src="${data.line_plot_url}" alt="Line Plot" style="max-width: 100%; height: auto;">
                        </div>
                        <div class="tab-pane fade" id="bar-plot" role="tabpanel" aria-labelledby="bar-plot-tab">
                            <img src="${data.bar_plot_url}" alt="Bar Plot" style="max-width: 100%; height: auto;">
                        </div>
                    </div>
                `;
            } else {
                console.error("Plot container not found");
            }
            
            setupDownloadButton("download-baseline", data.simulation_data.baseline, "baseline_results.json");
            setupDownloadButton("download-clamped", data.simulation_data.clamped, "clamped_results.json");
            
            var simulationModal = new bootstrap.Modal(document.getElementById('simulation-modal'));
            if (simulationModal) {
                simulationModal.show();
            } else {
                console.error("Simulation modal not found");
            }
        } else {
            console.error("Simulation failed:", data.message);
            alert("Simulation failed: " + data.message);
        }
    })
    .catch(error => {
        console.error("Error in fetch:", error);
        hideLoader();
        alert("An error occurred while running the simulation: " + error.message);
    });
}

function setupDownloadButton(buttonId, data, filename) {
    var button = document.getElementById(buttonId);
    if (button) {
        var blob = new Blob([JSON.stringify(data)], { type: "application/json" });
        var url = URL.createObjectURL(blob);
        button.setAttribute("href", url);
        button.setAttribute("download", filename);
    } else {
        console.error(`Download button with id '${buttonId}' not found`);
    }
}

function updateParameters() {
    showLoader();
    var csrftoken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    var parametersData = {};
    var formElements = document.getElementById("update_parameters_form").elements;
    for (var i = 0; i < formElements.length; i++) {
        if (formElements[i].tagName === 'INPUT' && formElements[i].value.trim() !== '') {
            parametersData[formElements[i].name] = parseFloat(formElements[i].value);
        }
    }

    fetch("/network-model/update_parameters/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrftoken
        },
        body: JSON.stringify(parametersData)
    })
    .then(response => response.json())
    .then(data => {
        hideLoader();
        if (data.success) {
            alert("Parameters updated successfully!");
        } else {
            console.error("Error:", data.message);
            alert("An error occurred while updating parameters.");
        }
    })
    .catch(error => {
        hideLoader();
        console.error("Error:", error);
        alert("An error occurred while updating parameters.");
    });
}