import streamlit as st
import ee
import folium
from streamlit_folium import st_folium


def scale_msi(image):
    opticalBands = image.select(
        ['B1', 'B2', 'B3']).multiply(0.0001)
    return image.addBands(opticalBands, None, True)


def mask_S2_clouds(image):
    qa = image.select('QA60')
    cloudBitMask = 1 << 10
    cirrusBitMask = 1 << 11
    opticalBands = image.select(
        ['B1', 'B2', 'B3'])

    mask_gt = opticalBands.select(['B1', 'B2', 'B3']) \
        .reduce(ee.Reducer.min()).gt(0)
    mask = qa.bitwiseAnd(cloudBitMask).eq(0) \
        .And(qa.bitwiseAnd(cirrusBitMask).eq(0))
    return image.updateMask(mask.And(mask_gt))


@st.cache_resource
def initialize_gee():
    try:
        ee.Initialize()
        return True
    except Exception as e:
        st.error(
            "GEE не инициализирован. Выполните аутентификацию через CLI: `earthengine authenticate`")
        return False


if not initialize_gee():
    st.stop()

try:
    baikal_geometry = ee.FeatureCollection(
        'projects/ee-airgit1/assets/baikal_shape')
except Exception as e:
    st.error("Ошибка загрузки геометрии озера Байкал")
    st.stop()

st.title("Картограмма концентрации хлорофилла \"а\" в озере Байкал")

main_container = st.container()
left_col, right_col = st.columns([1, 4])

with left_col:
    st.subheader("Введите даты")

    # Блок ввода дат
    start_date = st.date_input(
        "Начальная дата",
        value=st.session_state.get('start_date', '2020-07-20'),
        key="start_date_input"
    )
    end_date = st.date_input(
        "Конечная дата",
        value=st.session_state.get('end_date', '2020-07-30'),
        key="end_date_input"
    )

    run_analysis = st.button("Применить", use_container_width=True)

    if 'map_data' in st.session_state:
        st.divider()

if end_date < start_date:
    st.error("Конечная дата не может быть раньше начальной даты")
    st.stop()


def calculate_oc3(image):
    b1 = image.select('B1')
    b2 = image.select('B2')
    b3 = image.select('B3')

    max_b1b2 = b1.max(b2)
    ratio = max_b1b2.divide(b3)
    R = ratio.log10()

    a0 = 0.2389
    a1 = -1.9369
    a2 = 1.7627
    a3 = -3.0777
    a4 = -0.1054
    oc3_log = ee.Image.constant(a0).add(
        R.multiply(a1).add(R.pow(2).multiply(a2)).add(
            R.pow(3).multiply(a3)).add(R.pow(4).multiply(a4)
                                       ))

    oc3 = ee.Image(10).pow(oc3_log)

    return oc3.select(['constant'], ['oc3']).clip(baikal_geometry)


if run_analysis or 'map_data' not in st.session_state:
    with st.spinner('Загрузка и обработка данных...'):
        try:
            sentinel_collection = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                                   .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                                   .filterBounds(baikal_geometry)
                                   .map(mask_S2_clouds)
                                   .map(scale_msi)
                                   .select(['B1', 'B2', 'B3'])
                                   .map(calculate_oc3))

            oc3_median = sentinel_collection.mean()
            st.session_state.map_data = oc3_median
            st.session_state.start_date = start_date
            st.session_state.end_date = end_date
            st.success("Данные успешно обработаны!")

        except Exception as e:
            st.error(f"Ошибка при обработке данных: {e}")
            st.stop()


def add_ee_layer(map_obj, ee_image, vis_params, name):
    """Добавляет слой из Google Earth Engine на карту Folium."""
    try:
        map_id = ee.Image(ee_image).getMapId(vis_params)
        tile_url = map_id['tile_fetcher'].url_format

        folium.raster_layers.TileLayer(
            tiles=tile_url,
            name=name,
            attr='Google Earth Engine',
            overlay=True,
            control=True
        ).add_to(map_obj)
    except Exception as e:
        st.error(f"Ошибка добавления слоя GEE: {e}")


with right_col:
    if 'map_data' in st.session_state:
        st.subheader("Визуализация данных")
        viz_params = {
            'min': 0,
            'max': 5,
            'palette': ["#d6f9cb", "#0E4205"],
            'bands': 'oc3'
        }

        m = folium.Map(location=[53.5, 107],
                       zoom_start=5, tiles=None, width='150%',
                       height=700,
                       control_scale=True
                       )

        try:
            add_ee_layer(m, st.session_state.map_data,
                         viz_params, 'Хлорофилл \"а\"')

            fc = baikal_geometry.geometry()
            m.add_child(
                folium.GeoJson(
                    data=fc.getInfo(),
                    name='Байкал',
                    style_function=lambda x: {
                        'color': 'blue', 'fillOpacity': 0, 'weight': 3}
                )
            )

            legend_html = '''<div style="position: fixed; bottom: 50px; right: 50px; z-index:1000; 
            background-color: white; padding: 10px; border: 2px solid grey; 
            border-radius: 5px; font-family: Arial, sans-serif;">
            <div style="position: relative; height: 200px; width: 30px; margin-bottom: 5px;">
            <!-- Вертикальный градиент -->
            <div style="background: linear-gradient(to bottom, #d6f9cb, #0E4205); 
                        width: 15px; height: 100%; border: 1px solid #ccc; margin: 0 auto;"></div>
            <!-- Метки значений -->
            <div style="position: absolute; top: 0; left: 0; font-size: 12px;">0</div>
            <div style="position: absolute; bottom: 0; left: 0; font-size: 12px;">5</div>
            </div>
            </div>'''

            m.get_root().html.add_child(folium.Element(legend_html))

            st_folium(m, width=1200, height=700, returned_objects=[])

        except Exception as e:
            st.error(f"Ошибка при отображении карты: {e}")
