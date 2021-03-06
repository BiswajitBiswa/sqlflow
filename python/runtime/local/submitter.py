# Copyright 2020 The SQLFlow Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from runtime.dbapi import table_writer
from runtime.feature.column import FeatureColumn
from runtime.local.tensorflow_submitter.train import train as tf_train
from runtime.local.xgboost_submitter.evaluate import \
    evaluate as xgboost_evaluate
from runtime.local.xgboost_submitter.explain import explain as xgboost_explain
from runtime.local.xgboost_submitter.predict import pred as xgboost_pred
from runtime.local.xgboost_submitter.train import train as xgboost_train
from runtime.model.db import read_metadata_from_db
from runtime.model.model import EstimatorType, Model


def submit_local_train(datasource,
                       original_sql,
                       select,
                       validation_select,
                       estimator_string,
                       model_image,
                       feature_column_map,
                       label_column,
                       model_params,
                       train_params,
                       validation_params,
                       save,
                       load,
                       user=""):
    """This function run train task locally.

    Args:
        datasource: string
            Like: odps://access_id:access_key@service.com/api?
                         curr_project=test_ci&scheme=http
        select: string
            The SQL statement for selecting data for train
        validation_select: string
            Ths SQL statement for selecting data for validation
        estimator_string: string
            TensorFlow estimator name, Keras class name, or XGBoost
        model_image: string
            Docker image used to train this model,
            default: sqlflow/sqlflow:step
        feature_column_map: string
            A map of Python feature column IR.
        label_column: string
            Feature column instance describing the label.
        model_params: dict
            Params for training, crossponding to WITH clause
        train_params: dict
            Extra train params, will be passed to runtime.tensorflow.train
            or runtime.xgboost.train. Optional fields:
            - disk_cache: Use dmatrix disk cache if True, default: False.
            - batch_size: Split data to batches and train, default: 1.
            - epoch: Epochs to train, default: 1.
        validation_params: dict
            Params for validation.
        save: string
            Model name to be saved.
        load: string
            The pre-trained model name to load
        user: string
            Not used for local submitter, used in runtime.pai only.
    """
    if estimator_string.lower().startswith("xgboost"):
        train_func = xgboost_train
    else:
        train_func = tf_train

    return train_func(original_sql=original_sql,
                      model_image=model_image,
                      estimator_string=estimator_string,
                      datasource=datasource,
                      select=select,
                      validation_select=validation_select,
                      model_params=model_params,
                      train_params=train_params,
                      validation_params=validation_params,
                      feature_column_map=feature_column_map,
                      label_column=label_column,
                      save=save,
                      load=load)


def submit_local_pred(datasource,
                      original_sql,
                      select,
                      model_name,
                      label_column,
                      model_params,
                      result_table,
                      user=""):
    model = Model.load_from_db(datasource, model_name)
    if model.get_type() == EstimatorType.XGBOOST:
        xgboost_pred(datasource, select, result_table, label_column, model)
    else:
        raise NotImplementedError("not implemented model type: {}".format(
            model.get_type()))


def submit_local_evaluate(datasource,
                          original_sql,
                          select,
                          model_name,
                          model_params,
                          result_table,
                          user=""):
    model = Model.load_from_db(datasource, model_name)
    validation_metrics = model_params.get("validation.metrics",
                                          "Accuracy").split(",")
    label_fc = model.get_meta("label")
    assert isinstance(label_fc, FeatureColumn)
    pred_label_name = label_fc.get_field_desc()[0].name
    if model.get_type() == EstimatorType.XGBOOST:
        xgboost_evaluate(datasource, select, result_table, model,
                         pred_label_name, validation_metrics)
    else:
        raise NotImplementedError("not implemented model type: {}".format(
            model.get_type()))


def submit_local_explain(datasource,
                         original_sql,
                         select,
                         model_name,
                         model_params,
                         result_table,
                         explainer="TreeExplainer",
                         user=""):
    model = Model.load_from_db(datasource, model_name)
    summary_params = dict()
    for k in model_params:
        if k.startswith("summary."):
            summary_key = k.replace("summary.", "")
            summary_params[summary_key] = model_params[k]

    if model.get_type() == EstimatorType.XGBOOST:
        xgboost_explain(datasource, select, explainer, summary_params,
                        result_table, model)
    else:
        raise NotImplementedError("not implemented model type: {}".format(
            model.get_type()))


def submit_local_show_train(datasource, model_name):
    meta = read_metadata_from_db(datasource, model_name)
    original_sql = meta.get("original_sql")
    if not original_sql:
        raise ValueError("cannot find the train SQL statement")

    result_set = [(model_name, original_sql)]
    header = ["Model", "Train Statement"]
    writer = table_writer.ProtobufWriter(result_set, header)
    for line in writer.dump_strings():
        print(line)
