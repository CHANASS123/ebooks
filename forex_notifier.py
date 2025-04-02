# 服务器运行版本
from playwright.sync_api import sync_playwright
import pandas as pd
import time
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

# ✅ 改为 Playwright 实现
def get_forexfactory_events():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US"
        )
        page.goto("https://www.forexfactory.com/calendar", timeout=60000)

        # 等待页面元素出现（不要求“可见”，避免可视区域限制）
        page.wait_for_load_state("networkidle")
        page.wait_for_selector("tr.calendar__row", timeout=20000)
        page.wait_for_load_state("networkidle")  # 等页面加载稳定

        # 强制滚动加载完整页面（保险做法）
        rows = page.query_selector_all("tr.calendar__row")
        for row in rows:
            try:
                row.scroll_into_view_if_needed()
                time.sleep(0.1)
            except:
                continue

        results = []
        current_date = ''

        for row in page.query_selector_all("tr.calendar__row"):
            try:
                # 日期
                date_td = row.query_selector("td.calendar__cell.calendar__date")
                if date_td:
                    current_date = date_td.inner_text().strip()

                currency = row.query_selector("td.calendar__cell.calendar__currency").inner_text().strip()

                impact_span = row.query_selector("td.calendar__cell.calendar__impact span")
                impact_class = impact_span.get_attribute("class")
                if "impact-red" in impact_class:
                    impact = "High"
                elif "impact-org" in impact_class:
                    impact = "Medium"
                elif "impact-yel" in impact_class:
                    impact = "Low"
                else:
                    impact = "None"

                event_title = row.query_selector("span.calendar__event-title").inner_text().strip()

                def safe_text(selector):
                    try:
                        el = row.query_selector(selector)
                        return el.inner_text().strip() if el else ""
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
            except:
                continue

        browser.close()
        return pd.DataFrame(results)

# ✅ 以下部分未作修改，保持原样
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
        "desp": content.replace('\n', '\n\n')
    }
    requests.post(url, data=data)

# ✅ 主运行逻辑保持不变
if __name__ == "__main__":
    df = get_forexfactory_events()
    df_high = df[df['Impact'] == 'High']
    df_diff = filter_actual_forecast_diff(df_high)
    usd_jpy = get_usd_jpy_rate()
    us10y = get_us10y_yield()

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

        message = "📈 当前市场关键指标：\n\n"
        message += info_df.to_string(index=False)

        message += "\n\n📢 近日高影响力经济事件实际值与预期值不同：\n\n"
        if not df_diff.empty:
            buffer = StringIO()
            df_diff.to_string(buf=buffer, index=False)
            message += buffer.getvalue()
        else:
            message += "暂无实际值与预期值不同的数据。"

        message += "\n\n" + "—" * 30 + "\n\n"
        message += "📋 全部高影响力事件一览：\n\n"
        for _, row in df_high.iterrows():
            message += f"📅 {row['Date']} | {row['Currency']} | {row['Event']}\n预测: {row['Forecast']} | 公布: {row['Actual']} | 前值: {row['Previous']}\n\n"

        send_wechat_message("📢 交易提醒：高影响事件更新", message, "SCT274953T09n4FNpFYwAlDB9JsW7HcxJJ")
    else:
        send_wechat_message("📢 无高影响力事件", "今天无高影响力经济事件。", "SCT274953T09n4FNpFYwAlDB9JsW7HcxJJ")
