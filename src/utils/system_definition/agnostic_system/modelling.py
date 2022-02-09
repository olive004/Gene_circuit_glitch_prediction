from copy import copy
import logging
import numpy as np


class Deterministic():
    def __init__(self) -> None:
        pass

    def dxdt_RNA(self, copynumbers, interactions, creation_rates, degradation_rates):
        # dx_dt = a + x * k * x.T - x * ∂   for x=[A, B] 
        
        k = interactions
        x = copynumbers
        alpha = creation_rates

        # Create middle term for each species
        # THERE'S DEFINITELY A MORE EFFICIENT WAY TO DO THIS
        coupling = np.zeros(copynumbers.shape)
        for current_species in range(len(copynumbers)):
            coupling[current_species] = np.average(x * k[current_species] * x.T)

        print(interactions)
        print(copynumbers)
        print(creation_rates)
        print(degradation_rates)
        print(coupling)
        logging.debug(alpha - coupling - x * degradation_rates)
        # import sys
        # sys.exit()

        return alpha - coupling - x * degradation_rates

    def plot(self, data, legend_keys):
        from src.utils.visualisation.graph_drawer import VisODE
        VisODE().plot(data, legend_keys)
