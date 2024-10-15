document.addEventListener('DOMContentLoaded', function() {
    // Initialize Bootstrap components
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
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

    function checkModelState() {
        fetch("/network-model/check_model_state/")
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                console.log("Current model state:", data.current_concentrations);
            } else {
                console.error("Failed to get model state:", data.message);
            }
        })
        .catch(error => {
            console.error("Error checking model state:", error);
        });
    }

    function fetchNodesAndPopulateModal() {
        console.log("Fetching nodes...");
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
                        <td>${node.name}</td>
                        <td>
                            <div class="form-check">
                                <input class="form-check-input node-checkbox" type="checkbox" value="${node.id}" id="clamp_${node.id}" ${node.clamped ? 'checked' : ''}>
                                <label class="form-check-label" for="clamp_${node.id}">
                                    Clamp
                                </label>
                            </div>
                        </td>
                        <td>
                            <input type="number" step="any" class="form-control form-control-sm node-value" id="value_${node.id}" value="${node.current_value}" ${!node.clamped ? 'disabled' : ''}>
                        </td>
                        <td>${node.original_concentration}</td>
                    `;
                    nodeTrayBody.appendChild(row);
                });
    
                // Add event listeners to checkboxes
                document.querySelectorAll('.node-checkbox').forEach(checkbox => {
                    checkbox.addEventListener('change', function() {
                        const valueInput = this.closest('tr').querySelector('.node-value');
                        valueInput.disabled = !this.checked;
                        if (this.checked) {
                            valueInput.value = valueInput.value || "1"; // Default to 1 if empty
                        }
                    });
                });
    
                // Show the modal
                var nodeTrayModal = new bootstrap.Modal(document.getElementById('nodeTrayModal'));
                nodeTrayModal.show();
    
                // Add event listener to the Save Changes button
                document.getElementById("saveNodeTray").addEventListener("click", saveClampedNodes);
            })
            .catch(error => {
                console.error("Error fetching nodes:", error);
                alert("An error occurred while fetching nodes. Check the console for details.");
            });
    }
    
    function saveClampedNodes() {
        const clampedNodes = [];
        document.querySelectorAll("#nodeTrayBody tr").forEach(row => {
            const checkbox = row.querySelector('input[type="checkbox"]');
            const valueInput = row.querySelector('input[type="number"]');
            if (checkbox.checked) {
                clampedNodes.push({
                    id: checkbox.value,
                    value: parseFloat(valueInput.value) || 1 // Use 1 as default if value is empty or not a number
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
                bootstrap.Modal.getInstance(document.getElementById('nodeTrayModal')).hide();
            } else {
                alert("Error updating node clamping: " + (data.error || "Unknown error"));
            }
        })
        .catch(error => {
            console.error("Error:", error);
            alert("An error occurred while updating node clamping.");
        });
    }

    // Attach the event listener to the save button
    document.getElementById("saveNodeTray").addEventListener("click", saveClampedNodes);

    function runSimulation() {
        console.log("runSimulation function called");
    
        // Show the loader
        const loader = document.getElementById("loader");
        if (loader) {
            loader.style.display = "flex";
        } else {
            console.error("Loader element not found");
        }
    
        // Get CSRF token
        const csrftoken = document.querySelector('[name=csrfmiddlewaretoken]');
        if (!csrftoken) {
            console.error("CSRF token not found");
            alert("An error occurred: CSRF token not found");
            if (loader) loader.style.display = "none";
            return;
        }
    
        // Get execution parameters
        const executionStart = parseFloat(document.getElementById("execution_start").value) || 0;
        const executionEnd = parseFloat(document.getElementById("execution_end").value) || 100;
        const executionSteps = parseInt(document.getElementById("execution_steps").value) || 1000;
        console.log("Execution parameters:", { start: executionStart, end: executionEnd, steps: executionSteps });
    
        // Run simulation
        fetch("/network-model/run_simulation/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrftoken.value
            },
            body: JSON.stringify({
                execution_start: executionStart,
                execution_end: executionEnd,
                execution_steps: executionSteps
            })
        })
        .then(response => {
            console.log("Received response:", response);
            if (!response.ok) {
                return response.json().then(errorData => {
                    throw new Error(`HTTP error! status: ${response.status}, message: ${errorData.message}, traceback: ${errorData.traceback}`);
                });
            }
            return response.json();
        })
        .then(data => {
            console.log("Received data:", data);
            console.log("Initial concentrations:", data.initial_concentrations);
            console.log("Final concentrations:", data.final_concentrations);
            if (loader) {
                loader.style.display = "none";
            }
    
            if (data.success) {
                const plotContainer = document.getElementById("plot-container");
                if (plotContainer) {
                    plotContainer.innerHTML = `<img src="${data.bar_plot_url}" alt="Bar Plot" style="max-width: 100%; height: auto;">`;
                } else {
                    console.error("Plot container not found");
                }
    
                // Display initial and final concentrations
                const resultsContainer = document.getElementById("results-container");
                if (resultsContainer) {
                    let resultsHtml = "<h3>Simulation Results</h3><table><tr><th>Species</th><th>Initial Concentration</th><th>Final Concentration</th></tr>";
                    for (let species in data.final_concentrations) {
                        resultsHtml += `<tr>
                            <td>${species}</td>
                            <td>${data.initial_concentrations[species].toFixed(6)}</td>
                            <td>${data.final_concentrations[species].toFixed(6)}</td>
                        </tr>`;
                    }
                    resultsHtml += "</table>";
                    resultsContainer.innerHTML = resultsHtml;
                }
    
                const simulationModal = new bootstrap.Modal(document.getElementById('simulation-modal'));
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
            if (loader) {
                loader.style.display = "none";
            }
            alert("An error occurred while running the simulation: " + error.message);
        });
    }
});

window.addEventListener('beforeunload', function (e) {
    // Cancel the event
    e.preventDefault();
    // Chrome requires returnValue to be set
    e.returnValue = '';

    // Send cleanup request to the server
    navigator.sendBeacon('/network-model/cleanup-temp-file/', JSON.stringify({
        session_key: getSessionKey()
    }));
});

function getSessionKey() {
    return document.getElementById('session-key').value;
}



