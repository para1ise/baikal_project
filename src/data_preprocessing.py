import copy
from datetime import datetime, timedelta

import pandas as pd


def convert_degree_and_min_to_degree(
    _data_frame: pd.DataFrame, name_of_col: str
) -> pd.DataFrame:
    """Преобразует значения в указанной колонке DataFrame из формата
    градусы-минуты (например, "45 30.5") в десятичные градусы (например,
    "45.5083").

    Args:
        _data_frame (pd.DataFrame): исходный DataFrame с данными
            для преобразования
        name_of_col (str): название колонки, содержащей данные в формате
            градусы-минуты

    Returns:
        pd.DataFrame: новый DataFrame с преобразованными значениями
        в указанной колонке
    """

    data_frame = copy.copy(_data_frame)
    data_list = data_frame[name_of_col].tolist()
    for i, item in enumerate(data_list):
        integer, frac = item.split(" ")
        data_list[i] = integer + str(float(frac) / 60)[1:]
    data_frame[name_of_col] = data_list
    return data_frame


def convert_datetime_irkutsk(_data_frame: pd.DataFrame) -> pd.DataFrame:
    """Преобразует колонки DATE и TIME в таблице с иркутскими данными (UTC+8)
    в колонку datetime в формате UTC-0.

    Args:
        _data_frame (pd.DataFrame): DataFrame с исходными колонками
            'DATE' и 'TIME'

    Returns:
        pd.DataFrame: копию преобразованного _data_frame с:
        - Новой колонкой 'datetime' в формате UTC-0 вида '%Y-%m-%dT%H:%M:%S'
        - Удаленными колонками 'DATE' и 'TIME'
    """

    data_frame = copy.copy(_data_frame)
    converted_list = data_frame["DATE"].tolist()
    for i in range(converted_list.__len__()):
        tmp = converted_list[i].split("/")
        date = [tmp[-1], tmp[0], tmp[1]]
        converted_list[i] = (
            "-".join(date) + " " + data_frame["TIME"][i] + ":00"
        )
        dt_datetime = datetime.strptime(converted_list[i], "%Y-%m-%d %H:%M:%S")
        dt_datetime -= timedelta(hours=8)
        converted_list[i] = dt_datetime.strftime("%Y-%m-%dT%H:%M:%S")

    data_frame["datetime"] = converted_list
    data_frame = data_frame.drop(columns=["DATE", "TIME"])
    return data_frame


if __name__ == "__main__":
    df_irk = convert_datetime_irkutsk(pd.read_csv("../data/raw/irk_all.csv"))
    df_sev = pd.read_csv("../data/raw/sevastopol.csv")

    start_idx = df_irk.index.max() + 1
    df_sev.index = range(start_idx, start_idx + len(df_sev))

    for k in df_sev.datetime.index:
        dt_datetime = datetime.strptime(
            df_sev.loc[k, "datetime"], "%Y-%m-%d %H:%M:%S"
        )
        df_sev.loc[k, "datetime"] = dt_datetime.strftime("%Y-%m-%dT%H:%M:%S")

    df_sev.rename(
        columns={"Latitude": "LATITUDE", "Longitude": "LONGITUDE"},
        inplace=True,
    )

    pd.concat([df_irk, df_sev]).to_csv("../data/processed/chl_data.csv")
