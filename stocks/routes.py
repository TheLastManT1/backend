from config import app
import stocks.helpers
from flask import render_template, request

@app.route("/dgw", methods=["POST"])
@app.route("/getstocks", methods=["POST"])
def getstocks():
    body = stocks.helpers.request_to_dict(request.get_data(as_text=True)[:-1])
    request_type = body["request"]["query"]["type"]
    print(request_type)

    match request_type:
        case "getquotes":
            return stocks.helpers.get_quotes([y for (x, y) in body["request"]["query"]["list"]])
        case "getsymbol":
            return stocks.helpers.get_symbols(body["request"]["query"]["phrase"], int(body["request"]["query"]["count"]), int(body["request"]["query"]["offset"]))
        case "getchart":
            return stocks.helpers.get_chart(body["request"]["query"]["symbol"], body["request"]["query"]["range"])

    return "Not implemented", 501