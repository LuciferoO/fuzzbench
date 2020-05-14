# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions andsss
# limitations under the License.

# pylint: disable=missing-function-docstring
"""Tests for data_utils.py"""
import pandas as pd
import pandas.testing as pd_test
import pytest

from analysis import data_utils


def create_trial_data(trial_id, benchmark, fuzzer, reached_coverage,
                      experiment):
    """Utility function to create test trial data."""
    return pd.DataFrame([{
        'experiment': experiment,
        'benchmark': benchmark,
        'fuzzer': fuzzer,
        'trial_id': trial_id,
        'time_started': 0,
        'time_ended': 24,
        'time': t,
        'edges_covered': reached_coverage,
    } for t in range(10)])


def create_experiment_data(experiment='test_experiment'):
    """Utility function to create test experiment data."""
    return pd.concat([
        create_trial_data(0, 'libpng', 'afl', 100, experiment),
        create_trial_data(1, 'libpng', 'afl', 200, experiment),
        create_trial_data(2, 'libpng', 'libfuzzer', 200, experiment),
        create_trial_data(3, 'libpng', 'libfuzzer', 300, experiment),
        create_trial_data(4, 'libxml', 'afl', 1000, experiment),
        create_trial_data(5, 'libxml', 'afl', 1200, experiment),
        create_trial_data(6, 'libxml', 'libfuzzer', 600, experiment),
        create_trial_data(7, 'libxml', 'libfuzzer', 800, experiment),
    ])


def test_validate_data_empty():
    experiment_df = pd.DataFrame()
    with pytest.raises(ValueError, match="Empty"):
        data_utils.validate_data(experiment_df)


def test_drop_fuzzer_benchmark_trials_above_max():
    """Tests that drop_fuzzer_benchmark_trials_above_max drops trials for a
    fuzzer-benchmark if they are beyond the maximum number of trials per
    fuzzer-benchmark that we specify."""
    experiment_df = create_experiment_data()
    new_experiment_df = data_utils.drop_fuzzer_benchmark_trials_above_max(
        experiment_df, 1)
    # Sanity check test.
    assert len(new_experiment_df) < len(experiment_df)
    columns = ['benchmark', 'fuzzer']
    expected_result = pd.DataFrame([
        ['libpng', 'afl'],
        ['libpng', 'libfuzzer'],
        ['libxml', 'afl'],
        ['libxml', 'libfuzzer'],
    ],
                                   columns=columns)
    trials_per_fuzzer_benchmark = (new_experiment_df[[
        'benchmark', 'fuzzer', 'trial_id'
    ]].drop_duplicates())[columns]
    assert (trials_per_fuzzer_benchmark.values == expected_result.values).all()


def test_validate_data_missing_columns():
    experiment_df = create_experiment_data()
    experiment_df.drop(columns=['trial_id', 'time'], inplace=True)
    with pytest.raises(ValueError, match="Missing columns.*trial_id"):
        data_utils.validate_data(experiment_df)


def test_drop_uninteresting_columns():
    experiment_df = create_experiment_data()
    cleaned_df = data_utils.drop_uninteresting_columns(experiment_df)

    assert 'time_started' not in cleaned_df.columns


def test_clobber_experiments_data():
    """Tests that clobber experiments data clobbers stale snapshots from earlier
    experiments."""
    df = pd.concat(
        create_experiment_data('experiment-%d' % experiment_num)
        for experiment_num in range(3))
    df.reset_index(inplace=True)

    to_drop = df[(df.experiment == 'experiment-2') &
                 (df.benchmark == 'libpng') & (df.fuzzer == 'afl')].index
    df.drop(to_drop, inplace=True)

    experiments = list(df['experiment'].drop_duplicates().values)
    df = data_utils.clobber_experiments_data(df, experiments)

    columns = ['experiment', 'benchmark', 'fuzzer']
    expected_result = pd.DataFrame([
        ['experiment-2', 'libpng', 'libfuzzer'],
        ['experiment-2', 'libxml', 'afl'],
        ['experiment-2', 'libxml', 'libfuzzer'],
        ['experiment-1', 'libpng', 'afl'],
    ],
                                   columns=columns)
    expected_result.sort_index(inplace=True)
    assert (
        df[columns].drop_duplicates().values == expected_result.values).all()


def test_filter_fuzzers():
    experiment_df = create_experiment_data()
    fuzzers_to_keep = ['afl']
    filtered_df = data_utils.filter_fuzzers(experiment_df, fuzzers_to_keep)

    assert filtered_df.fuzzer.unique() == fuzzers_to_keep


def test_filter_benchmarks():
    experiment_df = create_experiment_data()
    benchmarks_to_keep = ['libpng']
    filtered_df = data_utils.filter_benchmarks(experiment_df,
                                               benchmarks_to_keep)

    assert filtered_df.benchmark.unique() == benchmarks_to_keep


def test_label_fuzzers_by_experiment():
    experiment_df = create_experiment_data()
    labeled_df = data_utils.label_fuzzers_by_experiment(experiment_df)

    expected_fuzzer_names = ['afl-test_experiment', 'libfuzzer-test_experiment']
    assert labeled_df.fuzzer.unique().tolist() == expected_fuzzer_names


def test_filter_max_time():
    experiment_df = create_experiment_data()
    max_time = 5
    filtered_df = data_utils.filter_max_time(experiment_df, max_time)
    expected_times = range(max_time + 1)
    assert filtered_df.time.unique().tolist() == list(expected_times)


def test_benchmark_snapshot():
    """Tests that the snapshot data contains only the latest timestamp for all
    trials, in case all trials have the same lengths."""
    experiment_df = create_experiment_data()
    benchmark_df = experiment_df[experiment_df.benchmark == 'libxml']
    snapshot_df = data_utils.get_benchmark_snapshot(benchmark_df)
    timestamps_per_trial = snapshot_df[['trial_id', 'time']]
    timestamps_per_trial.reset_index(drop=True, inplace=True)

    # The latest timestamp is 9 in the example data.
    expected_timestamps_per_trial = pd.DataFrame([{
        'trial_id': trial,
        'time': 9
    } for trial in range(4, 8)])
    assert timestamps_per_trial.equals(expected_timestamps_per_trial)


def test_fuzzers_with_not_enough_samples():
    experiment_df = create_experiment_data()
    # Drop one of the afl/libxml trials (trial id 5).
    experiment_df = experiment_df[experiment_df.trial_id != 5]
    benchmark_df = experiment_df[experiment_df.benchmark == 'libxml']
    snapshot_df = data_utils.get_benchmark_snapshot(benchmark_df)

    expected_fuzzers = ['afl']
    assert data_utils.get_fuzzers_with_not_enough_samples(
        snapshot_df) == expected_fuzzers


def test_get_experiment_snapshots():
    experiment_df = create_experiment_data()
    snapshots_df = data_utils.get_experiment_snapshots(experiment_df)
    timestamps_per_trial = snapshots_df[['trial_id', 'time']]

    expected_timestamps_per_trial = pd.DataFrame([{
        'trial_id': trial,
        'time': 9
    } for trial in range(8)])
    assert timestamps_per_trial.equals(expected_timestamps_per_trial)


def test_benchmark_summary():
    experiment_df = create_experiment_data()
    benchmark_df = experiment_df[experiment_df.benchmark == 'libxml']
    snapshot_df = data_utils.get_benchmark_snapshot(benchmark_df)
    summary = data_utils.benchmark_summary(snapshot_df)

    expected_summary = pd.DataFrame({
        'fuzzer': ['afl', 'libfuzzer'],
        'time': [9, 9],
        'count': [2, 2],
        'min': [1000, 600],
        'median': [1100, 700],
        'max': [1200, 800]
    }).set_index(['fuzzer', 'time']).astype(float)
    assert summary[['count', 'min', 'median', 'max']].equals(expected_summary)


def test_experiment_summary():
    experiment_df = create_experiment_data()
    snapshots_df = data_utils.get_experiment_snapshots(experiment_df)
    summary = data_utils.experiment_summary(snapshots_df)

    expected_summary = pd.DataFrame({
        'benchmark': ['libpng', 'libpng', 'libxml', 'libxml'],
        'fuzzer': ['libfuzzer', 'afl', 'afl', 'libfuzzer'],
        'time': [9, 9, 9, 9],
        'count': [2, 2, 2, 2],
        'min': [200, 100, 1000, 600],
        'median': [250, 150, 1100, 700],
        'max': [300, 200, 1200, 800]
    }).set_index(['benchmark', 'fuzzer', 'time']).astype(float)
    assert summary[['count', 'min', 'median', 'max']].equals(expected_summary)


def test_benchmark_rank_by_mean():
    experiment_df = create_experiment_data()
    benchmark_df = experiment_df[experiment_df.benchmark == 'libxml']
    snapshot_df = data_utils.get_benchmark_snapshot(benchmark_df)
    ranking = data_utils.benchmark_rank_by_mean(snapshot_df)

    expected_ranking = pd.Series(index=['afl', 'libfuzzer'], data=[1100, 700])
    assert ranking.equals(expected_ranking)


def test_benchmark_rank_by_median():
    experiment_df = create_experiment_data()
    benchmark_df = experiment_df[experiment_df.benchmark == 'libxml']
    snapshot_df = data_utils.get_benchmark_snapshot(benchmark_df)
    ranking = data_utils.benchmark_rank_by_median(snapshot_df)

    expected_ranking = pd.Series(index=['afl', 'libfuzzer'], data=[1100, 700])
    assert ranking.equals(expected_ranking)


def test_benchmark_rank_by_average_rank():
    experiment_df = create_experiment_data()
    benchmark_df = experiment_df[experiment_df.benchmark == 'libxml']
    snapshot_df = data_utils.get_benchmark_snapshot(benchmark_df)
    ranking = data_utils.benchmark_rank_by_average_rank(snapshot_df)

    expected_ranking = pd.Series(index=['afl', 'libfuzzer'], data=[3.5, 1.5])
    assert ranking.equals(expected_ranking)


def test_benchmark_rank_by_stat_test_wins():
    experiment_df = create_experiment_data()
    benchmark_df = experiment_df[experiment_df.benchmark == 'libxml']
    snapshot_df = data_utils.get_benchmark_snapshot(benchmark_df)
    ranking = data_utils.benchmark_rank_by_stat_test_wins(snapshot_df)

    expected_ranking = pd.Series(index=['libfuzzer', 'afl'], data=[0, 0])
    assert ranking.equals(expected_ranking)


def test_experiment_pivot_table():
    experiment_df = create_experiment_data()
    snapshots_df = data_utils.get_experiment_snapshots(experiment_df)
    pivot_table = data_utils.experiment_pivot_table(
        snapshots_df, data_utils.benchmark_rank_by_median)

    # yapf: disable
    expected_data = pd.DataFrame([
        {'benchmark': 'libpng', 'fuzzer': 'afl', 'median':  150},
        {'benchmark': 'libpng', 'fuzzer': 'libfuzzer', 'median':  250},
        {'benchmark': 'libxml', 'fuzzer': 'afl', 'median': 1100},
        {'benchmark': 'libxml', 'fuzzer': 'libfuzzer', 'median':  700},
    ])
    # yapf: enable
    expected_pivot_table = pd.pivot_table(expected_data,
                                          index=['benchmark'],
                                          columns=['fuzzer'],
                                          values='median')
    assert pivot_table.equals(expected_pivot_table)


def test_experiment_rank_by_average_rank():
    experiment_df = create_experiment_data()
    snapshots_df = data_utils.get_experiment_snapshots(experiment_df)
    ranking = data_utils.experiment_level_ranking(
        snapshots_df, data_utils.benchmark_rank_by_median,
        data_utils.experiment_rank_by_average_rank)

    expected_ranking = pd.Series(index=['afl', 'libfuzzer'], data=[1.5, 1.5])
    assert ranking.equals(expected_ranking)


def test_experiment_rank_by_num_firsts():
    experiment_df = create_experiment_data()
    snapshots_df = data_utils.get_experiment_snapshots(experiment_df)
    ranking = data_utils.experiment_level_ranking(
        snapshots_df, data_utils.benchmark_rank_by_median,
        data_utils.experiment_rank_by_num_firsts)

    expected_ranking = pd.Series(index=['libfuzzer', 'afl'], data=[1.0, 1.0])
    assert ranking.equals(expected_ranking)


def test_experiment_rank_by_average_normalized_score():
    experiment_df = create_experiment_data()
    snapshots_df = data_utils.get_experiment_snapshots(experiment_df)
    ranking = data_utils.experiment_level_ranking(
        snapshots_df, data_utils.benchmark_rank_by_median,
        data_utils.experiment_rank_by_average_normalized_score)

    expected_ranking = pd.Series(index=['libfuzzer', 'afl'],
                                 data=[81.81, 80.00])
    pd_test.assert_series_equal(ranking,
                                expected_ranking,
                                check_names=False,
                                check_less_precise=True)
