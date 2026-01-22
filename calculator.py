import streamlit as st
import pandas as pd
import io

# ==========================================
# 1. 基础配置
# ==========================================
st.set_page_config(page_title="亚马逊利润计算", layout="wide", page_icon="💰")

# ==========================================
# 🛑 新增：简易密码验证系统
# ==========================================
def check_password():
    """如果不输入正确密码，程序就会卡在这里，不往下执行"""
    
    # 定义你的密码（你可以随便改）
    CORRECT_PASSWORD = "xjdsb" 

    # 如果已经在 session 中标记为登录成功，直接放行
    if st.session_state.get("password_correct", False):
        return True

    # 显示输入框
    st.markdown("### 🔒 请输入访问密码")
    password_input = st.text_input("密码", type="password")

    if password_input:
        if password_input == CORRECT_PASSWORD:
            st.session_state["password_correct"] = True
            st.rerun()  # 密码正确，刷新页面进入
        else:
            st.error("❌ 密码错误，请重试")
    
    return False

# 如果密码检查没通过，直接停止运行下面的所有代码
if not check_password():
    st.stop()

# 默认汇率
DEFAULT_RATES = {
    "USD": 7.20, "CAD": 5.30, "GBP": 9.10,
    "EUR": 7.80, "SEK": 0.70, "PLN": 1.80
}

# 国家配置 (加拿大 VAT 5%)
COUNTRY_OPTIONS = {
    "US": {"currency": "USD", "vat": 0.00, "label": "🇺🇸 美国"},
    "CA": {"currency": "CAD", "vat": 0.05, "label": "🇨🇦 加拿大"},
    "UK": {"currency": "GBP", "vat": 0.20, "label": "🇬🇧 英国"},
    "DE": {"currency": "EUR", "vat": 0.19, "label": "🇩🇪 德国"},
    "FR": {"currency": "EUR", "vat": 0.20, "label": "🇫🇷 法国"},
    "IT": {"currency": "EUR", "vat": 0.22, "label": "🇮🇹 意大利"},
    "ES": {"currency": "EUR", "vat": 0.21, "label": "🇪🇸 西班牙"},
    "NL": {"currency": "EUR", "vat": 0.21, "label": "🇳🇱 荷兰"},
    "SE": {"currency": "SEK", "vat": 0.25, "label": "🇸🇪 瑞典"},
    "PL": {"currency": "PLN", "vat": 0.23, "label": "🇵🇱 波兰"},
    "BE": {"currency": "EUR", "vat": 0.21, "label": "🇧🇪 比利时"},
}

# 欧洲低价FBA门槛
LOW_PRICE_THRESHOLDS = {
    "UK": 10.0, "DE": 11.0, "FR": 12.0, "IT": 12.0, "ES": 12.0,
    "NL": 12.0, "BE": 12.0, "SE": 140.0, "PL": 55.0
}

# ==========================================
# 2. 侧边栏设置
# ==========================================
with st.sidebar:
    # 汇率设置
    with st.expander("💱 汇率管理", expanded=True):
        col_r1, col_r2 = st.columns(2)
        custom_rates = {}
        keys = list(DEFAULT_RATES.keys())
        for i, currency in enumerate(keys):
            target_col = col_r1 if i % 2 == 0 else col_r2
            custom_rates[currency] = target_col.number_input(
                f"{currency}",
                value=DEFAULT_RATES[currency],
                step=0.01,
                format="%.2f"
            )

    st.divider()

    # 目标市场
    selected_countries = st.multiselect(
        "目标市场",
        options=list(COUNTRY_OPTIONS.keys()),
        format_func=lambda x: COUNTRY_OPTIONS[x]['label'],
        default=["US", "DE", "UK"]
    )

    st.divider()

    # 物流参数
    st.subheader("📦 头程物流")
    logistics_type = st.radio("默认方式", ["海运 (9元)", "铁路 (12元)", "空运 (45元)"], horizontal=True)
    default_freight = 9.0
    if "铁路" in logistics_type: default_freight = 12.0
    if "空运" in logistics_type: default_freight = 45.0
    freight_rate = st.number_input("头程单价 (CNY/kg)", value=default_freight, step=0.5)


# ==========================================
# 3. 费用核心算法
# ==========================================

def get_referral_fee(country, price):
    """计算佣金"""
    if country == "US":
        if price <= 15: return price * 0.05
        if price <= 20: return price * 0.10
        return price * 0.17
    if country == "CA":
        if price <= 20: return price * 0.10
        return price * 0.17
    if country == "UK":
        if price <= 15: return price * 0.05
        if price <= 20: return price * 0.10
        if price <= 40: return price * 0.15
        return (40 * 0.15) + ((price - 40) * 0.07)
    if country in ["DE", "FR", "IT", "ES", "NL", "BE"]:
        if price <= 15: return price * 0.05
        if price <= 20: return price * 0.10
        if price <= 45: return price * 0.15
        return (45 * 0.15) + ((price - 45) * 0.07)
    if country == "SE":
        if price <= 175: return price * 0.05
        if price <= 230: return price * 0.10
        if price <= 470: return price * 0.15
        return (470 * 0.15) + ((price - 470) * 0.07)
    if country == "PL":
        if price <= 65: return price * 0.05
        if price <= 180: return price * 0.10
        return (180 * 0.10) + ((price - 180) * 0.07)
    return price * 0.15


def get_us_fba_fee(l, w, h, weight_g, price):
    """美国FBA逻辑"""
    l_in, m_in, s_in = sorted([l / 2.54, w / 2.54, h / 2.54], reverse=True)
    actual_lb = weight_g / 453.59237
    vol_lb = (l_in * m_in * s_in) / 139.0
    ship_lb = max(actual_lb, vol_lb)
    ship_oz = ship_lb * 16.0
    col_idx = 0 if price < 10 else (1 if price <= 50 else 2)
    is_small = (actual_lb * 16 <= 16) and (l_in <= 15) and (m_in <= 12) and (s_in <= 0.75)
    is_large = (actual_lb <= 20) and (l_in <= 18) and (m_in <= 14) and (s_in <= 8)
    if is_small:
        table = [(2, [2.43, 3.32, 3.58]), (4, [2.49, 3.42, 3.68]), (6, [2.56, 3.45, 3.71]), (8, [2.66, 3.54, 3.80]),
                 (10, [2.77, 3.68, 3.94]), (12, [2.82, 3.78, 4.04]), (14, [2.92, 3.91, 4.17]), (16, [2.95, 3.96, 4.22])]
        for max_oz, prices in table:
            if ship_oz <= max_oz: return prices[col_idx], f"小号标准({max_oz}oz)"
    elif is_large:
        table_oz = [(4, [2.91, 3.73, 3.99]), (8, [3.13, 3.95, 4.21]), (12, [3.38, 4.20, 4.46]),
                    (16, [3.78, 4.60, 4.86])]
        table_lb = [(1.25, [4.22, 5.04, 5.30]), (1.50, [4.60, 5.42, 5.68]), (1.75, [4.75, 5.57, 5.83]),
                    (2.00, [5.00, 5.82, 6.08]), (2.25, [5.10, 5.92, 6.18]), (2.50, [5.28, 6.10, 6.36]),
                    (2.75, [5.44, 6.26, 6.52]), (3.00, [5.85, 6.67, 6.93])]
        if ship_oz <= 16:
            for max_oz, prices in table_oz:
                if ship_oz <= max_oz: return prices[col_idx], f"大号标准({max_oz}oz)"
        elif ship_lb <= 3.0:
            for max_lb, prices in table_lb:
                if ship_lb <= max_lb: return prices[col_idx], f"大号标准({max_lb}lb)"
        else:
            return 999.0, "大号标准(>3lb)"
    return 999.0, "大件/异常"


def get_fba_fee(country, l, w, h, weight_kg, price):
    # 美国
    if country == "US": return get_us_fba_fee(l, w, h, weight_kg * 1000, price)

    dims = sorted([l, w, h], reverse=True)
    l_cm, m_cm, s_cm = dims

    # 加拿大: 仅实重
    if country == "CA":
        is_env = (weight_kg <= 0.5) and (l_cm <= 38) and (m_cm <= 27) and (s_cm <= 2)
        is_std = (weight_kg <= 9.0) and (l_cm <= 45) and (m_cm <= 35) and (s_cm <= 20)
        lookup_weight = weight_kg
        if is_env:
            for max_w, fee in [(0.1, 4.73), (0.2, 4.99), (0.3, 5.31), (0.4, 5.60), (0.5, 5.95)]:
                if lookup_weight <= max_w: return fee, "CA信封"
        elif is_std:
            ca_table = [(0.1, 6.28), (0.2, 6.49), (0.3, 6.74), (0.4, 7.13), (0.5, 7.65), (0.6, 7.84), (0.7, 8.17),
                        (0.8, 8.43), (0.9, 8.74), (1.0, 8.99), (1.1, 9.10), (1.2, 9.37), (1.3, 9.58), (1.4, 9.85),
                        (1.5, 10.17)]
            for max_w, fee in ca_table:
                if lookup_weight <= max_w: return fee, "CA标准"
            return 999.0, "CA标准(>1.5kg)"
        return 999.0, "CA大件"

    # ==============================================================================
    # 欧洲 (EU)
    # ==============================================================================
    vol_weight = (l * w * h) / 5000.0
    charge_weight_eu = max(weight_kg, vol_weight)
    real_weight_eu = weight_kg

    use_low = False
    thresh = LOW_PRICE_THRESHOLDS.get(country)
    if thresh and price <= thresh: use_low = True

    # -----------------------------------------------------------
    # A. 欧洲低价FBA表 (Low Price FBA) - 全看实重
    # -----------------------------------------------------------
    # 结构: (重量, L, W, H, 价格字典, "等级名称")
    if use_low:
        low_price_table = [
            # 轻信封 (5档)
            (0.02, 33, 23, 2.5,
             {"UK": 1.46, "DE": 1.61, "FR": 2.24, "IT": 2.64, "ES": 2.15, "NL": 1.96, "SE": 28.71, "PL": 1.68,
              "BE": 1.74}, "轻信封"),
            (0.04, 33, 23, 2.5,
             {"UK": 1.50, "DE": 1.64, "FR": 2.26, "IT": 2.65, "ES": 2.21, "NL": 2.00, "SE": 28.91, "PL": 1.70,
              "BE": 1.77}, "轻信封"),
            (0.06, 33, 23, 2.5,
             {"UK": 1.52, "DE": 1.66, "FR": 2.27, "IT": 2.67, "ES": 2.23, "NL": 2.00, "SE": 29.07, "PL": 1.70,
              "BE": 1.78}, "轻信封"),
            (0.08, 33, 23, 2.5,
             {"UK": 1.67, "DE": 1.80, "FR": 2.79, "IT": 2.79, "ES": 2.55, "NL": 2.08, "SE": 30.56, "PL": 1.72,
              "BE": 1.83}, "轻信封"),
            (0.10, 33, 23, 2.5,
             {"UK": 1.70, "DE": 1.83, "FR": 2.81, "IT": 2.81, "ES": 2.59, "NL": 2.11, "SE": 30.74, "PL": 1.73,
              "BE": 1.86}, "轻信封"),
            # 标准信封
            (0.21, 33, 23, 2.5,
             {"UK": 1.73, "DE": 1.86, "FR": 2.81, "IT": 2.81, "ES": 2.61, "NL": 2.16, "SE": 31.56, "PL": 1.74,
              "BE": 1.98}, "标准信封"),
            (0.46, 33, 23, 2.5,
             {"UK": 1.87, "DE": 2.02, "FR": 3.31, "IT": 3.04, "ES": 2.85, "NL": 2.25, "SE": 36.61, "PL": 1.83,
              "BE": 2.12}, "标准信封"),
            # 大/超大信封
            (0.96, 33, 23, 4.0,
             {"UK": 2.42, "DE": 2.39, "FR": 3.96, "IT": 3.35, "ES": 3.00, "NL": 2.91, "SE": 37.79, "PL": 1.89,
              "BE": 2.66}, "大信封"),
            (0.96, 33, 23, 6.0,
             {"UK": 2.65, "DE": 2.78, "FR": 4.31, "IT": 3.59, "ES": 3.23, "NL": 3.26, "SE": 40.84, "PL": 1.91,
              "BE": 2.96}, "超大信封"),
            # 小包裹
            (0.15, 35, 25, 12.0,
             {"UK": 2.67, "DE": 2.78, "FR": 4.31, "IT": 3.59, "ES": 3.23, "NL": 3.13, "SE": 41.23, "PL": 1.81,
              "BE": 2.64}, "小包裹"),
            (0.40, 35, 25, 12.0,
             {"UK": 2.70, "DE": 2.99, "FR": 4.71, "IT": 3.91, "ES": 3.46, "NL": 3.17, "SE": 43.31, "PL": 1.86,
              "BE": 2.96}, "小包裹"),
        ]

        for max_w, max_l, max_m, max_s, fees, name in low_price_table:
            # 低价全看实重
            if real_weight_eu <= max_w and l_cm <= max_l and m_cm <= max_m and s_cm <= max_s:
                fee = fees.get(country, 0)
                if fee > 0: return fee, f"低价-{name}"
        # 兜底到标准

    # -----------------------------------------------------------
    # B. 欧洲标准FBA表 (Standard FBA)
    # -----------------------------------------------------------

    # 1. 信封类 (看实重)
    envelopes_table = [
        # 轻信封
        (0.08, 33, 23, 2.5,
         {"UK": 2.07, "DE": 2.26, "FR": 3.30, "IT": 3.39, "ES": 3.21, "NL": 2.43, "SE": 35.08, "PL": 3.13, "BE": 2.41},
         "轻信封"),
        # 标准信封
        (0.21, 33, 23, 2.5,
         {"UK": 2.10, "DE": 2.31, "FR": 3.33, "IT": 3.45, "ES": 3.26, "NL": 2.49, "SE": 35.47, "PL": 3.16, "BE": 2.47},
         "标准信封"),
        (0.46, 33, 23, 2.5,
         {"UK": 2.16, "DE": 2.42, "FR": 3.77, "IT": 3.64, "ES": 3.45, "NL": 2.58, "SE": 41.09, "PL": 3.36, "BE": 2.56},
         "标准信封"),
        # 大信封
        (0.96, 33, 23, 4.0,
         {"UK": 2.72, "DE": 2.78, "FR": 4.39, "IT": 3.94, "ES": 3.60, "NL": 3.24, "SE": 42.35, "PL": 3.49, "BE": 3.21},
         "大信封"),
        # 超大信封
        (0.96, 33, 23, 6.0,
         {"UK": 2.94, "DE": 3.16, "FR": 4.72, "IT": 4.17, "ES": 3.85, "NL": 3.59, "SE": 45.62, "PL": 3.58, "BE": 3.53},
         "超大信封"),
    ]

    # 2. 包裹类 (看计费重)
    parcels_table = [
        # 小包裹
        (0.15, 35, 25, 12.0,
         {"UK": 2.91, "DE": 3.12, "FR": 4.56, "IT": 4.13, "ES": 3.52, "NL": 3.47, "SE": 45.41, "PL": 3.61, "BE": 3.39},
         "小包裹"),
        (0.40, 35, 25, 12.0,
         {"UK": 3.00, "DE": 3.13, "FR": 5.07, "IT": 4.54, "ES": 3.74, "NL": 3.51, "SE": 47.29, "PL": 3.67, "BE": 3.67},
         "小包裹"),
        (0.90, 35, 25, 12.0,
         {"UK": 3.04, "DE": 3.14, "FR": 5.79, "IT": 4.95, "ES": 3.95, "NL": 4.03, "SE": 48.19, "PL": 3.71, "BE": 4.15},
         "小包裹"),
        (1.40, 35, 25, 12.0,
         {"UK": 3.05, "DE": 3.15, "FR": 5.87, "IT": 5.11, "ES": 4.21, "NL": 4.50, "SE": 52.68, "PL": 3.76, "BE": 4.63},
         "小包裹"),
        (1.90, 35, 25, 12.0,
         {"UK": 3.25, "DE": 3.17, "FR": 6.10, "IT": 5.14, "ES": 4.27, "NL": 4.82, "SE": 54.49, "PL": 3.81, "BE": 4.95},
         "小包裹"),
        (3.90, 35, 25, 12.0,
         {"UK": 3.27, "DE": 4.28, "FR": 7.80, "IT": 5.16, "ES": 5.50, "NL": 5.90, "SE": 64.10, "PL": 3.93, "BE": 6.38},
         "小包裹"),
        # 标准包裹
        (0.15, 45, 34, 26.0,
         {"UK": 2.94, "DE": 3.13, "FR": 4.58, "IT": 4.29, "ES": 3.55, "NL": 3.62, "SE": 48.58, "PL": 3.67, "BE": 3.46},
         "标准包裹"),
        (0.40, 45, 34, 26.0,
         {"UK": 3.01, "DE": 3.16, "FR": 5.22, "IT": 4.70, "ES": 3.77, "NL": 3.97, "SE": 51.70, "PL": 3.73, "BE": 3.85},
         "标准包裹"),
        (0.90, 45, 34, 26.0,
         {"UK": 3.06, "DE": 3.18, "FR": 6.01, "IT": 5.15, "ES": 3.99, "NL": 4.32, "SE": 52.04, "PL": 3.80, "BE": 4.39},
         "标准包裹"),
        (1.40, 45, 34, 26.0,
         {"UK": 3.26, "DE": 3.67, "FR": 6.41, "IT": 5.26, "ES": 4.85, "NL": 4.65, "SE": 58.46, "PL": 3.89, "BE": 4.99},
         "标准包裹"),
        (1.90, 45, 34, 26.0,
         {"UK": 3.48, "DE": 3.69, "FR": 6.44, "IT": 5.29, "ES": 4.94, "NL": 4.69, "SE": 61.53, "PL": 3.97, "BE": 5.41},
         "标准包裹"),
        (2.90, 45, 34, 26.0,
         {"UK": 3.49, "DE": 4.29, "FR": 7.08, "IT": 5.30, "ES": 4.98, "NL": 4.75, "SE": 65.36, "PL": 4.10, "BE": 6.27},
         "标准包裹"),
        (3.90, 45, 34, 26.0,
         {"UK": 3.54, "DE": 4.83, "FR": 7.81, "IT": 5.35, "ES": 5.53, "NL": 5.08, "SE": 65.71, "PL": 4.15, "BE": 6.30},
         "标准包裹"),
        (5.90, 45, 34, 26.0,
         {"UK": 3.56, "DE": 4.96, "FR": 8.22, "IT": 5.38, "ES": 5.96, "NL": 5.23, "SE": 70.20, "PL": 4.19, "BE": 6.54},
         "标准包裹"),
        (8.90, 45, 34, 26.0,
         {"UK": 3.57, "DE": 5.77, "FR": 8.84, "IT": 5.41, "ES": 7.24, "NL": 5.67, "SE": 72.20, "PL": 4.24, "BE": 6.90},
         "标准包裹"),
        (11.9, 45, 34, 26.0,
         {"UK": 3.58, "DE": 6.39, "FR": 9.38, "IT": 6.25, "ES": 7.85, "NL": 6.24, "SE": 87.92, "PL": 4.37, "BE": 7.36},
         "标准包裹"),
    ]

    # 匹配逻辑: 优先匹配信封 (实重), 没匹配上再匹配包裹 (计费重)
    for max_w, max_l, max_m, max_s, fees, name in envelopes_table:
        if real_weight_eu <= max_w and l_cm <= max_l and m_cm <= max_m and s_cm <= max_s:
            fee = fees.get(country, 0)
            if fee > 0: return fee, f"标准-{name}"

    for max_w, max_l, max_m, max_s, fees, name in parcels_table:
        if charge_weight_eu <= max_w and l_cm <= max_l and m_cm <= max_m and s_cm <= max_s:
            fee = fees.get(country, 0)
            if fee > 0: return fee, f"标准-{name}"

    return 999.0, "超标"


# ==========================================
# 4. 主界面
# ==========================================

st.title("📊 亚马逊利润计算")
st.caption("操作说明：左侧可修改汇率。下方**表1**填产品参数，**表2**填售价(回车自动算)。")

# --- 表1：产品参数录入 ---
st.subheader("1. 产品基础参数")
if 'product_db' not in st.session_state:
    st.session_state.product_db = pd.DataFrame([
        {"SKU": "A001", "采购成本(¥)": 20.0, "重量(g)": 300, "长": 20.0, "宽": 15.0, "高": 5.0},
    ])

edited_products = st.data_editor(
    st.session_state.product_db,
    num_rows="dynamic",
    use_container_width=True,
    key="editor_products",
    # ⚠️ 修改点2：增加 column_config，精确控制小数位和步长
    column_config={
        "长": st.column_config.NumberColumn(
            label="长 (cm)", 
            min_value=0, 
            step=0.1,       # 允许输入 0.1 的倍数
            format="%.1f"   # 显示1位小数
        ),
        "宽": st.column_config.NumberColumn(
            label="宽 (cm)", 
            min_value=0, 
            step=0.1, 
            format="%.1f"
        ),
        "高": st.column_config.NumberColumn(
            label="高 (cm)", 
            min_value=0, 
            step=0.1, 
            format="%.1f"
        ),
        "采购成本(¥)": st.column_config.NumberColumn(label="采购成本(¥)", step=0.1, format="%.2f"),
        "重量(g)": st.column_config.NumberColumn(label="重量(g)", step=1),
    }
)

# --- 表2：动态计算矩阵 ---
st.subheader("2. 售价与利润 (实时计算)")

if not selected_countries:
    st.warning("请在左侧选择至少一个目标市场")
    st.stop()

# 准备数据
matrix_rows = []
valid_data_exists = False

for idx, row in edited_products.iterrows():
    sku = row.get("SKU", f"Prod-{idx}")


    def safe_get(key):
        val = row.get(key)
        if pd.isna(val) or val is None or val == "": return 0.0
        try:
            return float(val)
        except:
            return 0.0


    cost = safe_get("采购成本(¥)")
    w_g = safe_get("重量(g)")
    l = safe_get("长")
    w = safe_get("宽")
    h = safe_get("高")

    if w_g <= 0 or l <= 0 or w <= 0 or h <= 0: continue
    valid_data_exists = True

    # 头程
    vol_w = (l * w * h) / 5000.0
    ch_w = max(w_g / 1000.0, vol_w)
    freight_cny = ch_w * freight_rate

    for c in selected_countries:
        price_key = f"price_{sku}_{c}"
        if price_key not in st.session_state:
            st.session_state[price_key] = 19.99

        current_price = st.session_state[price_key]

        cfg = COUNTRY_OPTIONS[c]
        currency = cfg['currency']
        rate = custom_rates.get(currency, 1.0)

        referral = get_referral_fee(c, current_price)
        fba, fba_type = get_fba_fee(c, l, w, h, w_g / 1000.0, current_price)
        vat = (current_price / (1 + cfg["vat"])) * cfg["vat"]
        returns = current_price * 0.05

        platform_cost_cny = (referral + fba + vat + returns) * rate
        revenue_cny = current_price * rate
        profit = revenue_cny - cost - freight_cny - platform_cost_cny
        margin = (profit / revenue_cny) * 100 if revenue_cny > 0 else 0

        matrix_rows.append({
            "SKU": sku,
            "国家": cfg['label'],
            "售价 (编辑)": current_price,
            "利润 (¥)": round(profit, 2),
            "利润率 (%)": round(margin, 2),
            "FBA费": round(fba, 2),
            "FBA类型": fba_type,
            "key_id": price_key
        })

if not valid_data_exists:
    st.info("ℹ️ 暂无计算结果。请在上方表格完善【重量、长、宽、高】信息（需大于0）。")
else:
    df_matrix = pd.DataFrame(matrix_rows)

    edited_matrix = st.data_editor(
        df_matrix,
        column_config={
            "售价 (编辑)": st.column_config.NumberColumn(required=True, step=0.01, format="%.2f"),
            "利润 (¥)": st.column_config.NumberColumn(disabled=True, format="%.2f"),
            "利润率 (%)": st.column_config.NumberColumn(disabled=True, format="%.2f"),
            "FBA费": st.column_config.NumberColumn(disabled=True, format="%.2f"),
            "FBA类型": st.column_config.TextColumn(disabled=True),
            "key_id": None
        },
        use_container_width=True,
        hide_index=True,
        key="matrix_editor"
    )

    needs_rerun = False
    for index, row in edited_matrix.iterrows():
        key = row['key_id']
        new_price = row['售价 (编辑)']
        if key in st.session_state and st.session_state[key] != new_price:
            st.session_state[key] = new_price
            needs_rerun = True
    if needs_rerun: st.rerun()

    csv = edited_matrix.to_csv(index=False, encoding='utf-8-sig')

    st.download_button("📥 导出结果 CSV", csv, "profit_analysis.csv")


