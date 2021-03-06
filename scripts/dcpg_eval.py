#!/usr/bin/env python

"""Evaluates prediction performance of a DeepCpG model.

Imputes missing methylation states and evaluates model on observered states.

Example:
    dcpg_eval.py \
        ./data/*.h5 \
        --out_file ./eval.h5 \
        --out_report ./eval.tsv
"""

import sys
import os

import argparse
import logging

from deepcpg import data as dat
from deepcpg import evaluation as ev
from deepcpg import models as mod
from deepcpg.data import hdf
from deepcpg.utils import ProgressBar, to_list


class App(object):

    def run(self, args):
        name = os.path.basename(args[0])
        parser = self.create_parser(name)
        opts = parser.parse_args(args[1:])
        return self.main(name, opts)

    def create_parser(self, name):
        p = argparse.ArgumentParser(
            prog=name,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            description='Evaluates prediction performance of a DeepCpG model')
        p.add_argument(
            'data_files',
            help='Input data files for evaluation',
            nargs='+')
        p.add_argument(
            '--model_files',
            help='Model files',
            nargs='+')
        p.add_argument(
            '-o', '--out_report',
            help='Output report file with evaluation metrics')
        p.add_argument(
            '--out_data',
            help='Output file with predictions and labels')
        p.add_argument(
            '--replicate_names',
            help='Regex to select replicates',
            nargs='+')
        p.add_argument(
            '--nb_replicate',
            type=int,
            help='Maximum number of replicates')
        p.add_argument(
            '--batch_size',
            help='Batch size',
            type=int,
            default=128)
        p.add_argument(
            '--nb_sample',
            help='Number of samples',
            type=int)
        p.add_argument(
            '--verbose',
            help='More detailed log messages',
            action='store_true')
        p.add_argument(
            '--log_file',
            help='Write log messages to file')
        return p

    def main(self, name, opts):
        logging.basicConfig(filename=opts.log_file,
                            format='%(levelname)s (%(asctime)s): %(message)s')
        log = logging.getLogger(name)
        if opts.verbose:
            log.setLevel(logging.DEBUG)
        else:
            log.setLevel(logging.INFO)

        if not opts.model_files:
            raise ValueError('No model files provided!')

        log.info('Loading model ...')
        model = mod.load_model(opts.model_files)

        log.info('Loading data ...')
        nb_sample = dat.get_nb_sample(opts.data_files, opts.nb_sample)
        replicate_names = dat.get_replicate_names(
            opts.data_files[0],
            regex=opts.replicate_names,
            nb_key=opts.nb_replicate)
        data_reader = mod.data_reader_from_model(
            model, replicate_names, replicate_names=replicate_names)

        data_reader = data_reader(opts.data_files,
                                  nb_sample=nb_sample,
                                  batch_size=opts.batch_size,
                                  loop=False, shuffle=False)

        meta_reader = hdf.reader(opts.data_files, ['chromo', 'pos'],
                                 nb_sample=nb_sample,
                                 batch_size=opts.batch_size,
                                 loop=False, shuffle=False)

        log.info('Predicting ...')
        data = dict()
        progbar = ProgressBar(nb_sample, log.info)
        for inputs, outputs, weights in data_reader:
            batch_size = len(list(inputs.values())[0])
            progbar.update(batch_size)

            preds = to_list(model.predict(inputs))

            data_batch = dict()
            data_batch['preds'] = dict()
            data_batch['outputs'] = dict()
            for i, name in enumerate(model.output_names):
                data_batch['preds'][name] = preds[i].squeeze()
                data_batch['outputs'][name] = outputs[name].squeeze()

            for name, value in next(meta_reader).items():
                data_batch[name] = value
            dat.add_to_dict(data_batch, data)
        progbar.close()
        data = dat.stack_dict(data)

        report = ev.evaluate_outputs(data['outputs'], data['preds'])

        if opts.out_report:
            report.to_csv(opts.out_report, sep='\t', index=False)

        report = ev.unstack_report(report)
        print(report.to_string())

        if opts.out_data:
            hdf.write_data(data, opts.out_data)

        log.info('Done!')

        return 0


if __name__ == '__main__':
    app = App()
    app.run(sys.argv)
