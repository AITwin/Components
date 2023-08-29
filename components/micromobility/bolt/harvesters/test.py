import pandas as pd

# Sample DataFrame
data = {
    'ds': ['2023/08/29 00:00:00', '2023/08/29 00:00:00', '2023/08/29 00:30:00', '2023/08/29 00:45:00'],
    'y': [0, 0, 0, 0],
    'pred': [0.0, 0.0, 0.0, 0.0],
    'pred_upper': [1.925291e-09, 1.944851e-09, 2.115698e-09, 2.130890e-09],
    'pred_lower': [-1.991455e-09, -2.025970e-09, -2.050457e-09, -2.247598e-09],
    'area_id': [1, 1, 2, 2]
}

df = pd.DataFrame(data)

# Group by 'ds' and aggregate data into lists
result = df.groupby('ds').agg(
    area_id=pd.NamedAgg(column='area_id', aggfunc=list),
    pred_upper=pd.NamedAgg(column='pred_upper', aggfunc=list),
    pred_lower=pd.NamedAgg(column='pred_lower', aggfunc=list)
).reset_index()

print(result)
# Convert to a dictionary with 'ds' as keys
result_dict = {}
for index, row in result.iterrows():
    result_dict[row['ds']] = {
        'area_id': row['area_id'],
        'pred_upper': row['pred_upper'],
        'pred_lower': row['pred_lower']
    }

print(result_dict)
