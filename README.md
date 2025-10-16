# HTC Remanila Backend

## What is this
This backend, based on Flask, serves as a multi-purpose API platform. It provides several services, including weather, stocks, YouTube, Twitter and Facebook. The HTC phones can connect to this API and fetch up to date information

## Setting up and running
- Make sure your python version > 3.9, 3.11 recommend
- Change directory to the project root
- Create a virtual environment (optional, but highly recommended)
- Install dependencies

    Here are the commands to do this in most Linux distros
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip3 install -r requirements.txt
    ```

- Open `config.py` in your favourite text editor
- Modify the `HOST` variable to the current IP/domain of your server
- Enable/disable components depending on your needs
- For YouTube functionality, obtain an API key from the [Google Developers Console](https://console.developers.google.com/)
- Now run the server and enjoy!
    ```bash
    python3 app.py
    ```

## What next?
- [Patch your device](https://github.com/htc-remanila/resources)

## What's working?
- [x] Weather
    - [x] Weather based on coordinates
    - [x] Weather based on Accuweather codes
- [ ] Stocks
    - [x] Update symbols
    - [x] Search for symbols
    - [ ] Display graphs
- [ ] YouTube
    - [x] Load "Most viewed" feed as "Trending"
    - [ ] Load other feeds
    - [x] Load thumbnails
    - [x] Search
    - [ ] Reccomended videos based on current video
    - [ ] Video details
    - [x] Watch videos on h264 main profile capable devices
    - [ ] Watch videos on non-h264 main profile capable devices
- [ ] Twitter
- [ ] Facebook
