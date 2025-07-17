import ee
import pandas as pd


def scale_msi(image: ee.Image) -> ee.Image:
    """Масштабирует оптические каналы MSI/Sentinel-2 (MultiSpectral Instrument)
    из исходных целочисленных значений в спектральные коэффициенты отражения
    (reflectance).

    Умножает значения в выбранных оптических каналах (B2-B8A)
    на коэффициент 0.0001 для преобразования в диапазон (0;1).
    Заменяет исходные каналы в изображении масштабированными версиями.

    Args:
        image (ee.Image): Исходное изображение MSI/Sentinel-2.

    Returns:
        ee.Image: Изображение с заменёнными оптическими каналами
        в диапазоне (0;1).
    """

    opticalBands = image.select(
        ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A"]
    ).multiply(0.0001)
    return image.addBands(opticalBands, None, True)


def mask_s2_clouds(image: ee.Image) -> ee.Image:
    """Маскирует облака на изображениях MSI/Sentinel-2 по битам числа QA60,
    которое используется в качестве показателя качетва спутникого снимка.

    Args:
        image (ee.Image): Исходное изображение MSI/Sentinel-2.

    Returns:
        ee.Image: Изображение после применения маскировки.
    """

    qa = image.select("QA60")
    cloudBitMask = 1 << 10
    cirrusBitMask = 1 << 11
    selected_bands = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A"]
    opticalBands = image.select(selected_bands)

    mask_gt = (
        opticalBands.select(selected_bands).reduce(ee.Reducer.min()).gt(0)
    )
    mask = (
        qa.bitwiseAnd(cloudBitMask)
        .eq(0)
        .And(qa.bitwiseAnd(cirrusBitMask).eq(0))
    )
    return image.updateMask(mask.And(mask_gt))


def preproc(ic: ee.ImageCollection, df: pd.DataFrame) -> pd.DataFrame:
    """Извлекает значения коэффициента отражения для заданных точек и дат
    из коллекции изображений MSI/Sentinel-2 и сопоставляет измерения
    (концентрации хлорофилла-а).

    Для каждой точки в DataFrame:
    1. Создает временное окно ±1 день от указанной даты измерения
    2. Осуществляет поиск в ImageCollection по дате и координате измерения
    3. Применяет масштабирование и маскирование облаков на найденном снимке
    4. Извлекает медианные значения пикселя 20х20 квадратных метров
        для первого валидного изображения
    5. Сопоставляет концентрацию хлорофилла-а

    Args:
        ic (ee.ImageCollection): Исходная коллекция изображений Sentinel-2
        df (pd.DataFrame): DataFrame с точками наблюдений, должен
            содержать колонки:
            - 'datetime' (дата наблюдения в формате, распознаваемом ee.Date),
            - 'LATITUDE' (широта точки),
            - 'LONGITUDE' (долгота точки),
            - 'CHL' (концентарция хлорофилла-а в мкг/л)

    Returns:
        pd.DataFrame: DataFrame с извлеченными значениями каналов, где:
            - Индексы соответствуют номерам натурных измерений
            из входного DataFrame
            - Колонки соответствуют каналам Sentinel-2: ['B2','B3','B4','B5',
                                                'B6','B7','B8','B8A', 'CHL']
            - Значения представляют коэффициент отражения (диапазон (0;1))
            - Концентарция хлорофилла-а в мкг/л

    Пример выходной таблицы:
        index | B2    | B3    | B4    | ...
        ------|-------|-------|-------|-----
        0     | 0.123 | 0.256 | 0.189 | ...
        2     | 0.101 | 0.210 | 0.172 | ...
        ...   | ...   | ...   | ...   | ...

    Примечания:
    - Точки без валидных данных (облачность/отсутствие снимков) исключаются
    из выходного DataFrame
    """

    dict_stats = {
        key: value
        for key, value in zip(df.index.to_list(), df["datetime"].to_list())
    }
    for i in dict_stats:
        date_of_observation = ee.Date(df["datetime"][i])
        start_date = date_of_observation.advance(-1, "day")
        end_date = date_of_observation.advance(1, "day")

        images = (
            ic.filterDate(start_date, end_date)
            .filterBounds(
                ee.Geometry.Point(
                    float(df["LONGITUDE"][i]), float(df["LATITUDE"][i])
                )
            )
            .map(scale_msi)
            .map(mask_s2_clouds)
        )
        found_stats = None
        if images.size().getInfo():
            img = images.toList(images.size())
            for j in range(img.length().getInfo()):
                v_mean = (
                    ee.Image(img.get(j))
                    .reduceRegion(
                        reducer=ee.Reducer.median(),
                        geometry=ee.Geometry.Point(
                            float(df["LONGITUDE"][i]), float(df["LATITUDE"][i])
                        ),
                        scale=20,
                    )
                    .getInfo()
                )
                if v_mean["B3"] is not None:
                    found_stats = v_mean
                    break
        dict_stats[i] = found_stats

    for k, v in list(dict_stats.items()):
        if not v:
            del dict_stats[k]
    return (
        pd.DataFrame.from_dict(dict_stats, orient="index")
        .loc[:, ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A"]]
        .join(df_all["CHL"])
    )


if __name__ == "__main__":
    df_all = pd.read_csv("../data/processed/chl_data.csv")

    ee.Authenticate()
    ee.Initialize(project="ee-airgit1")

    ic_msi = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    preproc(ic_msi, df_all).to_csv("../data/processed/rrs_data.csv")
