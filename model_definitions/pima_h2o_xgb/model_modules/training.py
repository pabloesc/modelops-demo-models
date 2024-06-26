from teradataml import DataFrame
from aoa import (
    record_training_stats,
    save_plot,
    aoa_create_context,
    ModelContext
)
import os
import h2o
from h2o.automl import H2OAutoML

def check_java():
    import jdk
    # Determine the home directory of the current user
    user_home_dir = os.path.expanduser('~')
 
    # Construct the Java installation path in the user's home directory
    java_home_path = os.path.join(user_home_dir, '.jdk', 'jdk-17.0.9+9')
    # Set JAVA_HOME to the default or existing environment value
    os.environ['JAVA_HOME'] = os.getenv('JAVA_HOME', java_home_path)
 
    # Check if Java is already installed
    if not os.path.isdir(os.environ['JAVA_HOME']):
        print('Installing Java...')
 
        # Install Java in the user's home directory
        jdk.install('17', path=os.path.join(user_home_dir, '.jdk'))
 
        # Update JAVA_HOME and PATH after successful installation
        os.environ['JAVA_HOME'] = java_home_path
        os.environ['PATH'] = f"{os.environ.get('PATH')}:{os.environ.get('JAVA_HOME')}/bin"

        print(f"Java installed at {os.environ['JAVA_HOME']}")
    else:
        print(f"Java is installed at {os.environ['JAVA_HOME']}")

def train(context: ModelContext, **kwargs):
    aoa_create_context()

    feature_names = context.dataset_info.feature_names
    target_name = context.dataset_info.target_names[0]
    
    # read training dataset from Teradata and convert to pandas
    check_java()
    h2o.init()
    train_df = DataFrame.from_query(context.dataset_info.sql)
    train_hdf = h2o.H2OFrame(train_df.to_pandas())

    # convert target column to categorical
    train_hdf[target_name] = train_hdf[target_name].asfactor()

    print("Starting training...")
  
    # Execute AutoML on training data
    aml = H2OAutoML(max_models=context.hyperparams['max_models'], seed=context.hyperparams['seed'])
    aml.train(x=feature_names, y=target_name, training_frame=train_hdf)

    # Here we are getting the best GBM algorithm for demo purposes
    model = aml.get_best_model(algorithm="gbm")
    if not model:
        model = aml.leader

    print("Finished training")

    # export model artefacts
    mojo = model.download_mojo(path=context.artifact_output_path, get_genmodel_jar=True)
    new_mojo = os.path.join(os.path.abspath(os.getcwd()), context.artifact_output_path, "model.h2o")
    if os.path.isfile(new_mojo):
        print("The file already exists")
    else:
        # Rename the file
        os.rename(mojo, new_mojo)

    print("Saved trained model")

    try:
        model.varimp_plot(server=True, save_plot_path=os.path.join(os.path.abspath(os.getcwd()), context.artifact_output_path, "feature_importance.png"))
        fi = model.varimp(True)
        fix = fi[['variable','scaled_importance']]
        fis = fix.to_dict('records')
        feature_importance = {v['variable']:float(v['scaled_importance']) for (k,v) in enumerate(fis)}
    except:
        print("Warning: This model doesn't support feature importance (Stacked Ensemble)")
        aml.varimp_heatmap()
        save_plot('Feature Heatmap', context=context)
        feature_importance = {}

    record_training_stats(train_df,
                          features=feature_names,
                          targets=[target_name],
                          categorical=[target_name],
                          feature_importance=feature_importance,
                          context=context)
