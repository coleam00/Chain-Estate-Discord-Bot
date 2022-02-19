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
messageChannelId = os.environ["ChainEstateBotMessageChannelId"]
CHAIN_ID = 56
CONTRACT_ABI = '[{"inputs": [{"internalType": "address","name": "account","type": "address"}],"name": "balanceOf","outputs": [{"internalType": "uint256","name": "","type": "uint256"}],"stateMutability": "view","type": "function"}]'
BINANCE_RPC_URL = "https://bsc-dataseed.binance.org/"

timeBetweenStatGenerations = 600
timeBetweenMessagingStats = 20
numIterations = 100000

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
    balances = tracker["balances"].values()
    maxBalance = float(max(balances)) / 10.0 ** 18
    print(maxBalance)
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

    with open("data/tracker.json", "w") as trackerFile:
        json.dump(tracker, trackerFile)

    print(f"Number of transactions: {len(tracker['uniqueHashes'])}")

    await asyncio.sleep(timeBetweenStatGenerations)
    return


# Function to have the bot message in the token holder bracket statistics in the Discord server.
async def messageTokenStatistics(client):
    if not os.path.exists("data/tracker.json"):
        await asyncio.sleep(timeBetweenMessagingStats)
        return

    with open("data/tracker.json", "r") as jsonFile:
        trackerJson = json.load(jsonFile)

    brackets = trackerJson["brackets"]
    numHolders = 0
    for value in brackets.values():
        numHolders += value

    statsMessage = "Chain Estate DAO Token Holder Statistics:\n\n"
    for bracket, value in brackets.items():
        holderPercentage = '{:.2f}'.format((float(value)/float(numHolders))*100)
        statsMessage += f"{bracket}: {value} holders ({holderPercentage}%)\n"

    messageChannel = await client.fetch_channel(messageChannelId)
    await messageChannel.send(statsMessage)
    await asyncio.sleep(timeBetweenMessagingStats)
    return