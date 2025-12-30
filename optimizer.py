import random
import logging
from deap import base, creator, tools, algorithms
from backtester import TimeMachine

class StrategyOptimizer:
    """Genetic Algorithm Optimizer for Strategy Parameters (Stage 16)."""
    
    def __init__(self):
        # 1. Define Fitness (Maximize ROI)
        creator.create("FitnessMax", base.Fitness, weights=(1.0,))
        creator.create("Individual", list, fitness=creator.FitnessMax)
        
        self.toolbox = base.Toolbox()
        
        # 2. Define Genes (Parameters to tune)
        # Gene 0: take_profit_percent (10% to 200%)
        self.toolbox.register("attr_tp", random.uniform, 10.0, 200.0)
        # Gene 1: stop_loss_percent (5% to 50%)
        self.toolbox.register("attr_sl", random.uniform, 5.0, 50.0)
        # Gene 2: buy_amount (0.1 to 1.0 SOL)
        self.toolbox.register("attr_amt", random.uniform, 0.1, 1.0)
        
        # 3. Define Individual Structure
        self.toolbox.register("individual", tools.initCycle, creator.Individual,
                             (self.toolbox.attr_tp, self.toolbox.attr_sl, self.toolbox.attr_amt), n=1)
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        
        # 4. Define Evaluation Function
        self.toolbox.register("evaluate", self._evaluate_strategy)
        self.toolbox.register("mate", tools.cxTwoPoint)
        self.toolbox.register("mutate", tools.mutGaussian, mu=0, sigma=10, indpb=0.2)
        self.toolbox.register("select", tools.selTournament, tournsize=3)

    def _evaluate_strategy(self, individual):
        """Run backtest with gene parameters and return ROI."""
        tp, sl, amt = individual
        config = {
            "take_profit_percent": tp,
            "stop_loss_percent": sl,
            "buy_amount_sol": amt
        }
        
        # Run simulation (mocked for now)
        # In reality: result = TimeMachine().run_backtest(..., config)
        # Mock fitness: closer to TP=50, SL=20 gives better score
        score = 100 - abs(tp - 50) - abs(sl - 20)
        return (max(0, score),)

    def optimize(self, generations=5):
        """Run the evolution."""
        logging.info(f"🧬 Starting Genetic Optimization ({generations} gens)...")
        pop = self.toolbox.population(n=20)
        final_pop, logbook = algorithms.eaSimple(pop, self.toolbox, cxpb=0.5, mutpb=0.2, ngen=generations, verbose=False)
        
        best_ind = tools.selBest(final_pop, 1)[0]
        logging.info(f"🏆 Best Parameters Found: TP={best_ind[0]:.2f}%, SL={best_ind[1]:.2f}%, AMT={best_ind[2]:.2f} SOL")
        return best_ind

if __name__ == "__main__":
    opt = StrategyOptimizer()
    opt.optimize()
