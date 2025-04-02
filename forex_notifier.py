from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time  # ✅ 添加 time 模块用于滚动等待
import requests
from bs4 import BeautifulSoup
import re


headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_usd_jpy_rate():
    url = "https://es.investing.com/currencies/usd-jpy"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        tag = soup.find("div", {"data-test": "instrument-price-last"})
        if tag:
            return tag.text.strip()
        else:
            return "USD/JPY rate not found."
    else:
        return f"Error fetching USD/JPY rate: {response.status_code}"

def get_us10y_yield():
    url = "https://www.cnbc.com/quotes/US10Y"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        span = soup.find("span", class_="QuoteStrip-lastPrice")
        if span:
            return span.text.strip()
        else:
            return "US10Y yield not found."
    else:
        return f"Error fetching US10Y yield: {response.status_code}"

def get_forexfactory_events():
    options = Options()
#     options.add_argument("--headless")  # 如需无头运行可取消注释
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=options)

    driver.get("https://www.forexfactory.com/calendar")

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "tr.calendar__row"))
    )

    # ⬇️ 用 scrollIntoView() 强制每一行都进入视口，触发真正加载
    rows = driver.find_elements(By.CSS_SELECTOR, "tr.calendar__row")
    for row in rows:
        try:
            driver.execute_script("arguments[0].scrollIntoView();", row)
            time.sleep(0.2)  # 给页面反应时间
        except:
            continue


    rows = driver.find_elements(By.CSS_SELECTOR, "tr.calendar__row")
    current_date = ''
    results = []

    for row in rows:
        try:
            # 日期
            date_td = row.find_elements(By.CSS_SELECTOR, "td.calendar__cell.calendar__date")
            if date_td:
                date_span = date_td[0].find_element(By.CLASS_NAME, "date")
                current_date = date_span.text.strip()

            # 货币
            currency = row.find_element(By.CSS_SELECTOR, "td.calendar__cell.calendar__currency").text.strip()

            # Impact 图标 class 判断
            impact_icon = row.find_element(By.CSS_SELECTOR, "td.calendar__cell.calendar__impact span")
            impact_class = impact_icon.get_attribute("class")
            if "impact-red" in impact_class:
                impact = "High"
            elif "impact-org" in impact_class:
                impact = "Medium"
            elif "impact-yel" in impact_class:
                impact = "Low"
            else:
                impact = "None"

            # 事件
            event_title = row.find_element(By.CSS_SELECTOR, "span.calendar__event-title").text.strip()

            # Actual/Forecast/Previous（容错）
            def safe_text(selector):
                try:
                    return row.find_element(By.CSS_SELECTOR, selector).text.strip()
                except:
                    return ""

            actual = safe_text("td.calendar__cell.calendar__actual")
            forecast = safe_text("td.calendar__cell.calendar__forecast")
            previous = safe_text("td.calendar__cell.calendar__previous")

            results.append({
                "Date": current_date,
                "Currency": currency,
                "Impact": impact,
                "Event": event_title,
                "Actual": actual,
                "Forecast": forecast,
                "Previous": previous
            })
        except Exception:
            continue

    return pd.DataFrame(results)


def filter_actual_forecast_diff(df):
    filtered_rows = []

    def clean_number(val):
        val = val.replace('%', '').replace(',', '').strip().upper()
        try:
            if val.endswith('K'):
                return float(val[:-1]) * 1_000
            elif val.endswith('M'):
                return float(val[:-1]) * 1_000_000
            else:
                return float(val)
        except:
            raise ValueError(f"无法解析的数值: {val}")


    for _, row in df.iterrows():
        actual = row['Actual']
        forecast = row['Forecast']
        if actual and forecast:
            try:
                actual_val = clean_number(actual)
                forecast_val = clean_number(forecast)
                if actual_val != forecast_val:
                    filtered_rows.append(row)
            except:
                continue
    return pd.DataFrame(filtered_rows)


def send_wechat_message(title, content, sendkey):
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = {
        "title": title,
        "desp": content.replace('\n', '\n\n')  # 为了格式更清晰
    }
    requests.post(url, data=data)

# 运行脚本
if __name__ == "__main__":
    df = get_forexfactory_events()
    df_high = df[df['Impact'] == 'High']
    df_diff = filter_actual_forecast_diff(df_high)
    usd_jpy = get_usd_jpy_rate()
    us10y = get_us10y_yield()
#     print(f"USD/JPY Rate: {usd_jpy}")
#     print(f"US 10Y Yield: {us10y}")
    info_df = pd.DataFrame({
        "指标": ["USD/JPY Rate", "US 10Y Yield"],
        "数值": [usd_jpy, us10y]
    })
    print(info_df.to_string(index=False))
    print("\n📢 近日高影响力经济事件实际值与预期值不同：\n")
    print(df_diff.to_string(index=False))
    print("\n📢 近日高影响力经济事件一览（仅 High）：\n")
    print(df[df['Impact'] == 'High'].to_string(index=False))
    if not df_high.empty:
        from io import StringIO

        # ① 市场指标部分
        message = "📈 当前市场关键指标：\n\n"
        message += info_df.to_string(index=False)

        # ② 实际 ≠ 预测 的部分
        message += "\n\n📢 近日高影响力经济事件实际值与预期值不同：\n\n"
        if not df_diff.empty:
            buffer = StringIO()
            df_diff.to_string(buf=buffer, index=False)
            message += buffer.getvalue()
        else:
            message += "暂无实际值与预期值不同的数据。"

        # ③ 明显分隔线 + 全部高影响事件条目列表
        message += "\n\n" + "—" * 30 + "\n\n"
        message += "📋 全部高影响力事件一览：\n\n"
        for _, row in df_high.iterrows():
            message += f"📅 {row['Date']} | {row['Currency']} | {row['Event']}\n预测: {row['Forecast']} | 公布: {row['Actual']} | 前值: {row['Previous']}\n\n"

        # 发送微信
        send_wechat_message("📢 交易提醒：高影响事件更新", message, "SCT274953T09n4FNpFYwAlDB9JsW7HcxJJ")

    else:
        send_wechat_message("📢 无高影响力事件", "今天无高影响力经济事件。", "SCT274953T09n4FNpFYwAlDB9JsW7HcxJJ")
