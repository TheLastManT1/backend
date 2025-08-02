import xml.etree.ElementTree as ET
from flask import render_template, Response
from datetime import datetime, timezone
import yfinance as yf

def request_to_dict(request):
    def recurse(node):
        if node.tag == 'list':
            result_list = []
            for child in node:
                if list(child) or child.attrib:
                    child_value = recurse(child)
                else:
                    child_value = child.text.strip() if child.text else ''
                result_list.append((child.tag, child_value))
            return result_list

        result = {}
        if node.attrib:
            result.update(node.attrib)

        children = list(node)
        if children:
            for child in children:
                child_result = recurse(child)
                if child.tag in result:
                    if not isinstance(result[child.tag], list):
                        result[child.tag] = [result[child.tag]]
                    result[child.tag].append(child_result)
                else:
                    result[child.tag] = child_result
        else:
            text = node.text.strip() if node.text else ''
            if text:
                if not result:
                    result = text
                else:
                    result['text'] = text

        return result

    root = ET.fromstring(request)
    return {root.tag: recurse(root)}

def get_quotes(symbols):
    quotes_data = []

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            raw_timestamp = info.get('regularMarketTime')
            if raw_timestamp is not None:
                timestamp = datetime.fromtimestamp(raw_timestamp, tz=timezone.utc).timestamp()
            else:
                timestamp = datetime.utcnow().timestamp()

            name = info.get('longName', info.get('shortName', symbol))
            current_price = info.get('regularMarketPrice')
            previous_close = info.get('regularMarketPreviousClose')
            open_price = info.get('regularMarketOpen')
            day_high = info.get('regularMarketDayHigh')
            day_low = info.get('regularMarketDayLow')
            volume = info.get('regularMarketVolume')
            change = info.get('regularMarketChange')
            change_percent = info.get('regularMarketChangePercent')

            if change is None and current_price is not None and previous_close is not None:
                change = current_price - previous_close
            if change_percent is None and current_price is not None and previous_close is not None and previous_close != 0:
                change_percent = (change / previous_close) * 100 if change is not None else None


            link = f"https://finance.yahoo.com/quote/{symbol}"

            quote = {
                'name': name,
                'symbol': symbol,
                'timestamp': timestamp,
                'link': link,
                'price': f"{current_price:.2f}" if current_price is not None else "N/A",
                'change': {
                    'value': f"{change:+.2f}" if change is not None else "N/A",
                    'percent': f"{change_percent:+.2f}" if change_percent is not None else "N/A"
                },
                'open': f"{open_price:.2f}" if open_price is not None else "N/A",
                'high': f"{day_high:.2f}" if day_high is not None else "N/A",
                'low': f"{day_low:.2f}" if day_low is not None else "N/A",
                'volume': volume if volume is not None else "N/A"
            }
            quotes_data.append(quote)
        except Exception as e:
            raise Exception(f"Error fetching data for {symbol}: {e}")

    response_xml = render_template("stockquotes.xml", quotes=quotes_data)
    response = Response(response_xml, mimetype="application/xml; charset=utf-8")
    return response

def get_symbols(search_query, count, offset):
    quotes_data = []

    try:
        max_results_to_fetch = offset + count
        search_results = yf.Search(search_query, max_results=max_results_to_fetch).quotes

        relevant_results = search_results[offset : offset + count]

        for item in relevant_results:
            name = item.get('longname', item.get('shortname', item.get('symbol', 'N/A')))
            symbol = item.get('symbol', 'N/A')
            quotes_data.append({
                'name': name,
                'symbol': symbol
            })
    except Exception as e:
        raise Exception(f"Error searching for symbols with yfinance: {e}")

    response_xml = render_template("stocksymbols.xml", quotes=quotes_data)
    response = Response(response_xml, mimetype="application/xml; charset=utf-8")
    return response

def get_chart(symbol, chart_range):
    points_data = []
    symbol_meta = {}

    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info

        symbol_meta['name'] = info.get('longName', info.get('shortName', symbol))
        # marketopen and marketclose are not directly available in yfinance info.
        symbol_meta['marketopen'] = "N/A" # Placeholder
        symbol_meta['marketclose'] = "N/A" # Placeholder
        gmtoffset_ms = info.get('gmtOffSetMilliseconds', 0)
        symbol_meta['gmtoffset'] = int(gmtoffset_ms / 1000)
        symbol_meta['application_data'] = '\\Application Data\\HTC\\ygo\\'


        hist = ticker.history(period=chart_range if chart_range[-1] != 'm' else chart_range + 'o')

        for index, row in hist.iterrows():
            timestamp_unix = index.timestamp()
            close_price = row.get('Close')
            if close_price is not None:
                points_data.append({
                    'close': f"{close_price:.2f}",
                    'timestamp': f"{timestamp_unix:.1f}"
                })
    except Exception as e:
        raise Exception(f"Error fetching chart data for {symbol} with range {chart_range}: {e}")

    response_xml = render_template("stockchart.xml", points=points_data, symbol=symbol_meta)
    response = Response(response_xml, mimetype="application/xml; charset=utf-8")
    return response