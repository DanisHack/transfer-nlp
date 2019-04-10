"""
Runner class


You should define a json config file and place it into the /experiments folders
A CustomDataset class should be implemented, as well as a nn.Module, a Vectorizer and a Vocabulary (if the initial class is insufficient for the need)

This file aims at launching an experiments based on a config file

"""

import logging
from typing import Dict

import torch
from knockknock import slack_sender

from transfer_nlp.runners.runnersABC import RunnerABC
from transfer_nlp.runners.utils import update_train_state

name = 'transfer_nlp.runners.single_task'
logging.getLogger(name).setLevel(level=logging.INFO)
logger = logging.getLogger(name)
logging.info('')


class Runner(RunnerABC):

    def __init__(self, config_args: Dict):

        super().__init__(config_args=config_args)

    def train_one_epoch(self):

        self.epoch_index += 1
        sample_probability = (20 + self.epoch_index) / self.config_args['num_epochs']  # TODO: include this into the NMT training part

        self.training_state['epoch_index'] += 1

        # Set the dataset object to train mode such that the dataset used is the training data
        self.dataset.set_split(split='train')
        batch_generator = self.generator.generator(dataset=self.dataset, batch_size=self.config_args['batch_size'], device=self.config_args['device'])

        running_loss = 0
        running_metrics = {f"running_{metric}": 0 for metric in self.metrics.names}

        # Set the model object to train mode (torch optimizes the parameters)
        self.model.train()

        num_batch = self.dataset.get_num_batches(batch_size=self.config_args['batch_size'])

        for batch_index, batch_dict in enumerate(batch_generator):

            if batch_index % 30 == 0:
                logger.info(f"Training batch {batch_index + 1} / {num_batch}")
            self.optimizer.zero_grad()

            model_inputs = {inp: batch_dict[inp] for inp in self.model_inputs}
            y_pred = self.model(**model_inputs)

            loss_params = {
                "input": y_pred,
                "target": batch_dict['y_target']}

            if hasattr(self.loss.loss, 'mask') and self.mask_index:
                loss_params['mask_index'] = self.mask_index

            loss = self.loss.loss(**loss_params)
            penalty = self.regularizer.regularizer.compute_penalty_uniform(model=self.model)

            loss_batch = loss.item() + penalty.item()
            running_loss += (loss_batch - running_loss) / (batch_index + 1)

            loss.backward()
            # Gradient clipping
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config_args['gradient_clipping'])

            self.optimizer.step()

            for metric in self.metrics.names:
                metric_batch = self.metrics.metrics[metric](**loss_params)
                running_metrics[f"running_{metric}"] += (metric_batch - running_metrics[f"running_{metric}"]) / (batch_index + 1)

        self.training_state['train_loss'].append(running_loss)
        for metric in self.metrics.names:
            self.training_state[f"train_{metric}"].append(running_metrics[f"running_{metric}"])

        # Iterate over validation dataset
        self.dataset.set_split(split='val')
        batch_generator = self.generator.generator(dataset=self.dataset, batch_size=self.config_args['batch_size'], device=self.config_args['device'])

        running_loss = 0
        running_metrics = {f"running_{metric}": 0 for metric in self.metrics.names}

        # Set the model object to val mode (torch does not optimize the parameters)
        self.model.eval()

        num_batch = self.dataset.get_num_batches(batch_size=self.config_args['batch_size'])

        for batch_index, batch_dict in enumerate(batch_generator):

            if batch_index % 30 == 0:
                logger.info(f"Validation batch {batch_index + 1} / {num_batch}")

            model_inputs = {inp: batch_dict[inp] for inp in self.model_inputs}
            y_pred = self.model(**model_inputs)

            loss_params = {
                "input": y_pred,
                "target": batch_dict['y_target']}

            if hasattr(self.loss.loss, 'mask') and self.mask_index:
                loss_params['mask_index'] = self.mask_index

            loss = self.loss.loss(**loss_params)
            penalty = self.regularizer.regularizer.compute_penalty_uniform(model=self.model)

            loss_batch = loss.item() + penalty.item()
            running_loss += (loss_batch - running_loss) / (batch_index + 1)

            for metric in self.metrics.names:
                metric_batch = self.metrics.metrics[metric](**loss_params)
                running_metrics[f"running_{metric}"] += (metric_batch - running_metrics[f"running_{metric}"]) / (batch_index + 1)

        self.training_state['val_loss'].append(running_loss)

        for metric in self.metrics.names:
            self.training_state[f"val_{metric}"].append(running_metrics[f"running_{metric}"])

        self.training_state = update_train_state(config_args=self.config_args, model=self.model,
                                                 train_state=self.training_state)
        self.scheduler.scheduler.step(self.training_state['val_loss'][-1])

    def do_test(self):

        self.dataset.set_split(split='test')
        batch_generator = self.generator.generator(dataset=self.dataset, batch_size=self.config_args['batch_size'], device=self.config_args['device'])
        num_batch = self.dataset.get_num_batches(batch_size=self.config_args['batch_size'])

        running_loss = 0
        running_metrics = {f"running_{metric}": 0 for metric in self.metrics.names}
        self.model.eval()

        for batch_index, batch_dict in enumerate(batch_generator):

            if batch_index % 30 == 0:
                logger.info(f"Test batch {batch_index + 1} / {num_batch}")

            model_inputs = {inp: batch_dict[inp] for inp in self.model_inputs}
            y_pred = self.model(**model_inputs)

            loss_params = {
                "input": y_pred,
                "target": batch_dict['y_target']}
            if hasattr(self.loss.loss, 'mask') and self.mask_index:
                loss_params['mask_index'] = self.mask_index

            loss = self.loss.loss(**loss_params)
            penalty = self.regularizer.regularizer.compute_penalty_uniform(model=self.model)

            loss_batch = loss.item() + penalty.item()

            running_loss += (loss_batch - running_loss) / (batch_index + 1)

            for metric in self.metrics.names:
                metric_batch = self.metrics.metrics[metric](**loss_params)
                running_metrics[f"running_{metric}"] += (metric_batch - running_metrics[f"running_{metric}"]) / (batch_index + 1)

        self.training_state['test_loss'] = running_loss
        for metric in self.metrics.names:
            self.training_state[f"test_{metric}"].append(running_metrics[f"running_{metric}"])


slack_webhook_url = "YourWebhookURL"
slack_channel = "YourFavoriteSlackChannel"


@slack_sender(webhook_url=slack_webhook_url, channel=slack_channel)
def run_with_slack(runner, test_at_the_end: bool = False):
    runner.run(test_at_the_end=test_at_the_end)


if __name__ == "__main__":
    import argparse

    logger.info('Starting...')

    parser = argparse.ArgumentParser(description="launch an experiment")

    parser.add_argument('--config', type=str)
    args = parser.parse_args()

    args.config = args.config or 'experiments/mlp.json'
    runner = Runner.load_from_project(experiment_file=args.config)

    if slack_webhook_url and slack_webhook_url != "YourWebhookURL":
        run_with_slack(runner=runner, test_at_the_end=False)
    else:
        runner.run(test_at_the_end=False)