from web3 import Web3
import requests
import time
import json
import os
import discord
import asyncio
import time
import threading

API_KEY = os.environ["CovalenthqApiKey"]
CONTRACT_ADDRESS = os.environ["CovalenthqContractAddress"]
defaultChannelId = os.environ["ChainEstateBotMessageChannelId"]
CHAIN_ID = 56
CONTRACT_ABI = '[{"inputs": [{"internalType": "address","name": "account","type": "address"}],"name": "balanceOf","outputs": [{"internalType": "uint256","name": "","type": "uint256"}],"stateMutability": "view","type": "function"}]'
BINANCE_RPC_URL = "https://bsc-dataseed.binance.org/"

defaultExcludedAddresses = [
    "0x965C421073f0aD56a11b2E3aFB80C451038F6178", "0x4abAc87EeC0AD0932B71037b5d1fc88B7aC2Defd",
    "0x9406B17dE6949aB3F32e7c6044b0b29e1987f9ab", "0xB164Eb7844F3A05Fd3eF01CF05Ac4961a74D47fF",
    "0x000000000000000000000000000000000000dEaD"
]

defaultTimeBetweenStatGenerations = 600
defaultTimeBetweenMessagingStats = 20
numIterations = 100000

configItems = ["contractAddress", "channelId", "timeBetweenStatGenerations", "timeBetweenMessagingStats", "addExcludedAddress"]

# Wrapper function to call generateTokenStatistics so there isn't a huge stack trace.
async def callGenerateTokenStatistics():
    for i in range(numIterations):
        await generateTokenStatistics()

    await callGenerateTokenStatistics()

# Wrapper function to call messageTokenStatistics so there isn't a huge stack trace.
async def callMessageTokenStatistics(client):
    for i in range(numIterations):
        await messageTokenStatistics(client)

    await callMessageTokenStatistics(client)

# Function to generate the Chain Estate DAO token holder statistics using the covalenthq API.
async def generateTokenStatistics():
    provider = Web3.HTTPProvider(BINANCE_RPC_URL)
    w3 = Web3(provider)
    token = w3.eth.contract(address=Web3.toChecksumAddress(CONTRACT_ADDRESS), abi=CONTRACT_ABI)

    contractAddress = CONTRACT_ADDRESS
    timeBetweenStatGenerations = defaultTimeBetweenStatGenerations
    timeBetweenMessagingStats = defaultTimeBetweenMessagingStats
    excludedAddresses = defaultExcludedAddresses

    if os.path.exists("config.json"):
        with open("config.json", "r") as configFile:
            configJson = json.load(configFile)

        if "contractAddress" in configJson:
            contractAddress = configJson["contractAddress"]
        if "timeBetweenStatGenerations" in configJson:
            timeBetweenStatGenerations = configJson["timeBetweenStatGenerations"]
        if "addExcludedAddresses" in configJson:
            excludedAddresses = configJson["addExcludedAddresses"]

    if not os.path.exists("data"):
        os.mkdir("data")

    if not os.path.exists("data/tracker.json"):
        with open("data/tracker.json", "w") as jsonFile:
            json.dump({"lastBlockHeight": 0, "balances": {}, "brackets": {}, "transfers": [], "uniqueHashes": []}, jsonFile)

    response = requests.get(f"https://api.covalenthq.com/v1/56/block_v2/latest/?key={API_KEY}")
    responseJson = response.json()

    if responseJson["error"]:
        print("Error getting block height.")
        return

    with open("data/tracker.json", "r") as trackerFile:
        tracker = json.load(trackerFile)

    blockHeight = int(responseJson["data"]["items"][0]["height"])
    startingBlock = tracker["lastBlockHeight"] if tracker["lastBlockHeight"] >= blockHeight - 10000 else blockHeight - 10000
    tracker["lastBlockHeight"] = blockHeight

    print(f"Block height: {blockHeight}")
    
    requestURL = f"https://api.covalenthq.com/v1/{CHAIN_ID}/events/address/{CONTRACT_ADDRESS}/?starting-block={startingBlock}&ending-block={blockHeight}&key={API_KEY}"
    print(requestURL)
    response = requests.get(requestURL)
    eventLogs = response.json()

    if eventLogs["error"]:
        print("Error getting event logs.")
        return

    events = eventLogs["data"]["items"]
    for event in events:
        transactionHash = event["tx_hash"]
        blockTimeStamp = event["block_signed_at"]
        params = event["decoded"]["params"]
        sender = params[0]["value"]
        receiver = params[1]["value"]
        value = params[2]["value"]
        uniqueHash = f"{transactionHash}|{sender}|{receiver}|{value}"
        eventName = event["decoded"]["name"]

        if eventName == "Transfer" and uniqueHash not in tracker["uniqueHashes"]:
            senderTokenBalance = token.functions.balanceOf(Web3.toChecksumAddress(sender)).call()
            tracker["balances"][sender] = senderTokenBalance

            receiverTokenBalance = token.functions.balanceOf(Web3.toChecksumAddress(receiver)).call()
            tracker["balances"][receiver] = receiverTokenBalance

            tracker["transfers"].append({"sender": sender, "receiver": receiver, "blockTimeStamp": blockTimeStamp, "transactionHash": transactionHash, "value": value})
            tracker["uniqueHashes"].append(uniqueHash)

    tracker["brackets"] = {}
    balances = []
    for address, balance in tracker["balances"].items():
        if address not in excludedAddresses:
            balances.append(balance)

    maxBalance = float(max(balances)) / 10.0 ** 18
    print(f"Max balance is: {maxBalance}")
    numDigits = len(str(int(maxBalance))) - 1
    startingDigits = 3
    currDigits = startingDigits
    startingNum = int("1" + "0"*currDigits)
    endingNum = int("1" + "0"*numDigits)
    
    while currDigits <= numDigits:
        currNum = int("1" + "0"*currDigits)
        if currDigits == startingDigits:
            tracker["brackets"][f"less than {currNum:,}"] = 0
        valRange = f"{currNum:,}+" if currDigits == numDigits else f"{currNum:,} - {int(str(currNum) + '0'):,}"
        tracker["brackets"][valRange] = 0
        currDigits += 1

    for balance in balances:
        balance = float(balance) / 10.0 ** 18
        if balance < startingNum and balance != 0:
            tracker["brackets"][f"less than {startingNum:,}"] += 1
        elif balance >= endingNum:
            tracker["brackets"][f"{endingNum:,}+"] += 1
        else:
            for bracket in [b for b in tracker["brackets"].keys() if b not in [f"less than {startingNum:,}", f"{endingNum:,}+"]]:
                bottom = int(bracket.split(" - ")[0].replace(",", ""))
                top = int(bracket.split(" - ")[1].replace(",", ""))

                if balance >= bottom and balance < top:
                    tracker["brackets"][bracket] += 1
                    break

    if os.path.exists("data/tracker.json"):
        with open("data/tracker.json", "w") as trackerFile:
            json.dump(tracker, trackerFile)

        print(f"Number of transactions: {len(tracker['uniqueHashes'])}")

    await asyncio.sleep(int(timeBetweenStatGenerations))
    return


# Function to have the bot message in the token holder bracket statistics in the Discord server.
async def messageTokenStatistics(client):
    if not os.path.exists("data/tracker.json"):
        await asyncio.sleep(timeBetweenMessagingStats)
        return

    with open("data/tracker.json", "r") as jsonFile:
        trackerJson = json.load(jsonFile)

    channelId = defaultChannelId
    timeBetweenMessagingStats = defaultTimeBetweenMessagingStats

    if os.path.exists("config.json"):
        with open("config.json", "r") as configFile:
            configJson = json.load(configFile)

        if "channelId" in configJson:
            channelId = configJson["channelId"]
        if "timeBetweenMessagingStats" in configJson:
            timeBetweenMessagingStats = configJson["timeBetweenMessagingStats"]

    brackets = trackerJson["brackets"]
    numHolders = 0
    for value in brackets.values():
        numHolders += value

    statsMessage = "Chain Estate DAO Token Holder Statistics:\n\n"
    for bracket, value in brackets.items():
        holderPercentage = '{:.2f}'.format((float(value)/float(numHolders))*100)
        statsMessage += f"{bracket}: {value} holders ({holderPercentage}%)\n"

    messageChannel = await client.fetch_channel(channelId)
    await messageChannel.send(statsMessage)
    await asyncio.sleep(int(timeBetweenMessagingStats))
    return

# Function to set the contract address, time between stat generations, time between stat messages, and the channel ID to message
async def setConfig(message):
    messageArgs = message.content.split(' ')
    if len(messageArgs) != 3:
        await message.channel.send("Invalid arguments for the command.")
        return

    configItem = messageArgs[1]
    configValue = messageArgs[2]

    if configItem not in configItems:
        await message.channel.send("Config item to change must be contractAddress, channelId, timeBetweenStatGenerations, timeBetweenMessagingStats, or addExcludedAddress.")
        return

    if configItem == "addExcludedAddress":
        configValue = [configValue]

    if not os.path.exists("config.json"):
        configJson = {configItem: configValue}
        with open("config.json", "w") as configFile:
            json.dump(configJson, configFile)
    else:
        with open("config.json", "r") as configFile:
            configJson = json.load(configFile)

        if configItem == "addExcludedAddress":
            if configItem in configJson.keys():
                configJson[configItem] = configJson[configItem] + configValue
            else:
                configJson[configItem] = configValue
        else:
            configJson[configItem] = configValue

        with open("config.json", "w") as configFile:
            json.dump(configJson, configFile)

    await message.channel.send(f"Set {configItem} to {configValue}")

# Function to delete tracker.json when a contract address is changed.
async def resetStats(message):
    os.remove("data/tracker.json")
    await messasge.channel.send("Deleted the tracker JSON file to reset the token holding statistics.")