import chromalyzer

config = {
    # Path to the CSV file containing the labels
    "labels_path": "data/labels.csv",
    
    # Name of the column in the labels.csv that contains the labels
    "label_column_name": "label",
    
    # Directory where generated heatmaps are stored
    "output_dir_heatmap": "/usr/scratch/chromalyzer/TII_aligned/",
    
    # Directory where generated plots will be saved
    "plot_dir": "/usr/scratch/chromalyzer/plots2/",
    
    # Boolean flag indicating whether all samples should be processed
    "all_samples": True,
    
    # Name of the sample to be analyzed if all_samples is False
    "sample_name": "230823_07_Green_River_Shale_Soil_500uLDCM_100oC24h.csv",
    # "sample_name": "230823_04_Murchison_Soil_300uLDCM_100oC24h-001.csv",

    "csv_file_name_column": "csv_file_name",
    
    # What m/z value to plot
    "m_z": "102"
}

chromalyzer.plot_heatmap.plot_heatmap(config)
