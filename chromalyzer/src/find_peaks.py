import itertools
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import matplotlib.pyplot as plt
import os
import json
import argparse
import concurrent.futures
from loguru import logger
from scipy.spatial.distance import cdist
from .utils.heatmap_utils import create_folder_if_not_exists, load_headmaps_list
from .utils.misc import *
from sklearn.cluster import DBSCAN


def get_cluster_rectangles(clusters, points):
    """
    Get the smallest rectangle containing each cluster.
    """
    rectangles = []
    for cluster in clusters:
        cluster_points = points[list(cluster)]
        min_row, min_col = np.min(cluster_points, axis=0)
        max_row, max_col = np.max(cluster_points, axis=0)
        rectangles.append((min_row, min_col, max_row, max_col))
    return rectangles

def find_clusters(points, threshold, min_points=20):
    """
    Find clusters of points using DBSCAN algorithm.
    """
    # # Limit the number of points to 100000 to avoid memory error
    if len(points) > 100000:
        return []

    # Apply DBSCAN
    dbscan = DBSCAN(eps=threshold, min_samples=min_points)
    cluster_labels = dbscan.fit_predict(points)

    # Organize points into clusters
    clusters = []
    for label in set(cluster_labels):
        if label != -1:  # -1 represents noise in DBSCAN
            cluster = np.where(cluster_labels == label)[0]
            clusters.append(set(cluster))

    return clusters

def find_peaks(filtered_binary,threshold = 5, rt1_timestep = 3.504, rt2_timestep = 0.008):
    coordinates = np.column_stack(np.where(filtered_binary))

    clusters = find_clusters(coordinates, threshold)

    cluster_rectangles = get_cluster_rectangles(clusters, coordinates)

    cluster_centers = []

    for cluster in cluster_rectangles:
        cluster_centers.append(find_center_indices(cluster))

    return cluster_centers,cluster_rectangles

# Calculates the summation of the area of the rectangle
def rectanle_sum_area(arr, rect):
    # Unpack the rectangle coordinates
    start_row, start_col, end_row, end_col = rect
    # Initialize sum
    total = 0
    # Iterate over the rows and columns in the rectangle
    for row in range(start_row, end_row + 1):
        for col in range(start_col, end_col + 1):
            total += arr[row][col]
    return total

def remove_noisy_columns_peaks(df_peaks, ht_df_mean_subtracted, sample):
    df_peaks = df_peaks.copy()
    column_noises = ht_df_mean_subtracted.columns[(ht_df_mean_subtracted != 0).all()].unique()

    distance = 50
    for column_noise in column_noises:

        df_peaks_to_remove = df_peaks[(df_peaks['csv_file_name'] == sample) & (df_peaks['RT1_center'] >= column_noise - distance) & (df_peaks['RT1_center'] <= column_noise + distance)].index

        df_peaks.drop(df_peaks_to_remove, inplace=True)
    return df_peaks

def remove_specified_columns_peaks(df_peaks, ht_df, sample, noise_columns, max_distance_removal_noisy_columns=50, non_zero_ratio_column_threshold=0.1):
    df_peaks = df_peaks.copy()

    for column in noise_columns:
        
        column_closest = ht_df.columns[np.abs(ht_df.columns - column).argmin()]
        column_non_zero_count = np.count_nonzero(ht_df.loc[:,ht_df.columns[(ht_df.columns > column_closest - max_distance_removal_noisy_columns) & (ht_df.columns < column_closest + max_distance_removal_noisy_columns)]].values)

        non_zero_percentage_column = column_non_zero_count/(ht_df[column_closest].values.reshape(-1).shape[0]+1)

        if non_zero_percentage_column > non_zero_ratio_column_threshold:

            df_peaks_to_remove = df_peaks[(df_peaks['csv_file_name'] == sample) & (df_peaks['RT1_center'] >= column_closest - max_distance_removal_noisy_columns) & (df_peaks['RT1_center'] <= column_closest + max_distance_removal_noisy_columns)].index
            
            df_peaks.drop(df_peaks_to_remove, inplace=True)
    
    return df_peaks

def remove_noisy_regions_peaks(df_peaks, ht_df, sample, noisy_region):
    df_peaks = df_peaks.copy()
    rt1_range_start = -np.inf if noisy_region['first_time_start'] == -1 else noisy_region['first_time_start']
    rt2_range_start = -np.inf if noisy_region['second_time_start'] == -1 else noisy_region['second_time_start']
    rt1_range_end = np.inf if noisy_region['first_time_end'] == -1 else noisy_region['first_time_end']
    rt2_range_end = np.inf if noisy_region['second_time_end'] == -1 else noisy_region['second_time_end']
    non_zero_ratio_region_threshold = noisy_region['non_zero_ratio_region_threshold']

    ht_df_values = ht_df.loc[rt2_range_end:rt2_range_start, ht_df.columns[(ht_df.columns > rt1_range_start) & (ht_df.columns < rt1_range_end)]].values.reshape(-1)
    non_zero_count = np.count_nonzero(ht_df_values)
    non_zero_percentage = non_zero_count/(ht_df_values.shape[0]+1)

    if non_zero_percentage > non_zero_ratio_region_threshold:
        df_peaks_to_remove = df_peaks[(df_peaks['csv_file_name'] == sample) & (df_peaks['RT1_center'] >= rt1_range_start) & (df_peaks['RT1_center'] <= rt1_range_end) &
                                       (df_peaks['RT2_center'] >= rt2_range_start) & (df_peaks['RT2_center'] <= rt2_range_end)].index
        
        df_peaks.drop(df_peaks_to_remove, inplace=True)
    
    return df_peaks

def convolution_filter(df_peaks, sample, windows,ht_df_filtered,non_zero_ratio_lambda3_filter):
    df_peaks = df_peaks.copy()
    for rt2_range, rt1_range in windows:

        rt1_range_start, rt1_range_end = rt1_range
        rt2_range_start, rt2_range_end = rt2_range

        selected_segment = ht_df_filtered.loc[rt2_range_end:rt2_range_start, ht_df_filtered.columns[(ht_df_filtered.columns > rt1_range_start) & (ht_df_filtered.columns < rt1_range_end)]].values
        non_zero_count_filtered = np.count_nonzero(selected_segment)
        non_zero_percentage_filtered = non_zero_count_filtered/(selected_segment.reshape(-1).shape[0]+1)

        if non_zero_percentage_filtered > non_zero_ratio_lambda3_filter:
            df_peaks.drop(df_peaks[(df_peaks['csv_file_name'] == sample) & (df_peaks['RT1_center'] >= rt1_range_start) & (df_peaks['RT1_center'] <= rt1_range_end) & 
                                (df_peaks['RT2_center'] >= rt2_range_start) & (df_peaks['RT2_center'] <= rt2_range_end)].index, inplace=True)

    return df_peaks

def extract_peaks_process(save_peaks_path, config,params):
    samples = pd.read_csv(config['labels_path'])
    samples_name = samples[config['csv_file_name_column']].tolist()

    first_time_axis = np.load(os.path.join(config['output_dir_TII_aligned'], f'first_time.npy'))
    second_time_axis = np.load(os.path.join(config['output_dir_TII_aligned'], f'second_time.npy'))

    rt1_axis = np.load(os.path.join(config['output_dir_TII_aligned'], 'first_time.npy'))
    rt2_axis = np.load(os.path.join(config['output_dir_TII_aligned'], 'second_time.npy'))
    rt1_timestep = round(rt1_axis[1] - rt1_axis[0],3)
    rt2_timestep = round(rt2_axis[0] - rt2_axis[1],3)

    
    for param in params:
        lam1 = param[0]
        lam2 = param[1]
        m_z = int(param[2])

        heatmaps = load_headmaps_list(config['output_dir_TII_aligned'],samples_name,m_z)

        df_peaks_list = []
        for idx, sample in enumerate(samples_name):
            
            # Skip the sample if it has no heatmap
            ht_df = heatmaps[idx]
            if len(ht_df) == 0: continue

            heatmap_numpy = ht_df.to_numpy()
            max = np.max(heatmap_numpy.reshape(-1))
            filtered = (heatmap_numpy >= max*lam1)

            ht_df_filtered = ht_df.where(ht_df >= max/lam2, 0)
            # Overall non-zero ratio filtering
            if config['overall_filter']['enable']:
                non_zero_count_filtered = np.count_nonzero(ht_df_filtered)
                non_zero_percentage_filtered = non_zero_count_filtered/(ht_df_filtered.values.reshape(-1).shape[0]+1)
                if non_zero_percentage_filtered > config['overall_filter']['non_zero_ratio_filter']:
                    df_peaks = pd.DataFrame([], columns=['csv_file_name', 'peak_area','RT1_center', 'RT2_center', 'RT1_start', 'RT2_start', 'RT1_end', 'RT2_end'])
                    continue
            
            cluster_centers,cluster_rectangles = find_peaks(filtered, threshold=config['peak_max_neighbor_distance'], rt1_timestep=rt1_timestep, rt2_timestep=rt2_timestep)

            

            # Adding actual time values to the peaks instead of indices
            peaks_pairs = []
            # Filter the peaks based on the area
            for id, point in enumerate(cluster_centers):
                intensity = rectanle_sum_area(heatmap_numpy,cluster_rectangles[id])
                if intensity >= lam2*max:
                    peaks_pairs.append((sample,intensity, first_time_axis[point[1]],second_time_axis[point[0]],
                                            first_time_axis[cluster_rectangles[id][1]],second_time_axis[cluster_rectangles[id][0]],
                                            first_time_axis[cluster_rectangles[id][3]],second_time_axis[cluster_rectangles[id][2]]))

            if len(peaks_pairs) == 0: continue

            

            df_peaks = pd.DataFrame(peaks_pairs, columns=['csv_file_name', 'peak_area','RT1_center', 'RT2_center', 'RT1_start', 'RT2_start', 'RT1_end', 'RT2_end'])

            if config['strict_noise_filtering']:
                # Remove peaks that occur near noisy column
                # df_peaks = remove_noisy_columns_peaks(df_peaks, ht_df_mean_subtracted, sample)

                # Remove noisy columns
                # if config['column_noise_removal']['enable']:
                    
                #     ht_df_filtered = ht_df.where(ht_df >= max/config['column_noise_removal']['lambda'], 0)
                #     df_peaks = remove_specified_columns_peaks(df_peaks, ht_df_filtered, sample, 
                #                                                 config['column_noise_removal']['noisy_columns'],
                #                                                 config['column_noise_removal']['max_distance_removal_noisy_columns'],
                #                                                 config['column_noise_removal']['non_zero_ratio_column_threshold'])
                    
                
                if config['enable_noisy_regions']:
                    # Removing peaks that occur in noisy regions
                    for noisy_region in config['noisy_regions']:
                        df_peaks = remove_noisy_regions_peaks(df_peaks, ht_df_filtered, sample, noisy_region)
                
                # # If first_time is greater than 11400, then that's noise (Visual inspection)
                # df_peaks.drop(df_peaks[df_peaks['RT1_center'] > config['max_retention_time1_allowed']].index, inplace=True)

                if config['convolution_filter']['enable']:
                    # Convolution filtering
                    windows = generate_windows(ht_df.index.min(), ht_df.index.max(), config['convolution_filter']['rt2_window_size'], 
                                                config['convolution_filter']['rt2_stride'], ht_df.columns.min(), ht_df.columns.max(), 
                                                config['convolution_filter']['rt1_window_size'], 
                                                config['convolution_filter']['rt1_stride'])
                    ht_df_filtered = ht_df.where(ht_df >= max/config['convolution_filter']['lambda3'], 0)
                    df_peaks = convolution_filter(df_peaks, sample, windows, ht_df_filtered, config['convolution_filter']['non_zero_ratio_lambda3_filter'])

                # If RT1_end - RT1_start is greater than delta_rt1, then that's noise
                df_peaks.drop(df_peaks[abs(df_peaks['RT1_end'] - df_peaks['RT1_start']) > config['delta_rt1']].index, inplace=True)

                # If RT2_start - RT2_end is greater than delta_rt2, then that's noise
                df_peaks.drop(df_peaks[abs(df_peaks['RT2_start'] - df_peaks['RT2_end']) > config['delta_rt2']].index, inplace=True)

                

            df_peaks_list.append(df_peaks)

        logger.info(f'Saving peaks for m/z value: {m_z}')
        if len(df_peaks_list) == 0:
            df_all_peaks = pd.DataFrame([], columns=['csv_file_name', 'peak_area','RT1_center', 'RT2_center', 'RT1_start', 'RT2_start', 'RT1_end', 'RT2_end'])

            df_all_peaks.to_csv(os.path.join(save_peaks_path, f'{m_z}.csv'), index=False)
        else:
            # Concatenate the peaks from all samples
            df_all_peaks = pd.concat(df_peaks_list)
            # Dropping peaks with area less than the threshold

            # df_all_peaks = df_all_peaks[(df_all_peaks['peak_area'] >= config['area_min_threshold'])]
            
            df_all_peaks.to_csv(os.path.join(save_peaks_path, f'{m_z}.csv'), index=False)
        
def extract_peaks(config):
    log_path = os.path.join(config['peaks_dir_path'], 'find_peaks.log')
    logger.add(log_path, rotation="10 MB")
    
    lambda1 = config['lambda1']
    lambda2 = config['lambda2']
    parallel_processing = config['parallel_processing']

    lam1 = [lambda1]
    lam2 = [lambda2]
    m_zs = pd.read_csv(config['mz_list_path'])
    m_z_list = m_zs[config['m_z_column_name']].tolist()
    params_combination = list(itertools.product(lam1,lam2,m_z_list))

    save_peaks_path = os.path.join(config['peaks_dir_path'], f'peaks_lambda1_{lambda1}/',f'lam2_{lambda2}/')
    create_folder_if_not_exists(save_peaks_path)

    # Split the parameters into multiple splits for parallel processing
    num_splits = config['number_of_splits'] if parallel_processing else 1
    params_splits = np.array_split(params_combination, num_splits)

    if parallel_processing:
        with concurrent.futures.ProcessPoolExecutor(max_workers=config['number_of_splits']) as executor:
            executor.map(extract_peaks_process, itertools.repeat(save_peaks_path), itertools.repeat(config), params_splits)
    else:
        extract_peaks_process(save_peaks_path, config, params_combination)
    
    logger.info('Peaks extraction is done.')