import discord
import sys
import os
import json
import datetime

from BotPrograms.TokenStatistics import *

intents = discord.Intents.all()
client = discord.Client(intents=intents)

adminUsers = ["colepm#6118", "Zachlm#3699"]

@client.event
async def on_ready():
    print(f'Chain Estate DAO bot is logged in as {client.user}')

    print("Generating token statistics.")
    await callGenerateTokenStatistics()

# Stops users from sending too many messages.
# No more than 2 messages per 10 seconds.
# No more than 10 messages per minute.
async def rateLimit(message, userJson):
    # First time this user has messaged, so they're good to go and add the current time as their last message.
    currTime = datetime.datetime.now()
    currTimeStr = datetime.datetime.strftime(currTime, "%m/%d/%Y, %H:%M:%S")
    if "lastMessageTenSec" not in userJson.keys():
        userJson["lastMessageTenSec"] = currTimeStr
        userJson["lastMessageMinute"] = currTimeStr
        userJson["numMessagesInTenSec"] = 1
        userJson["numMessagesInMinute"] = 1
        return False

    # Otherwise, this user has messaged before so make sure they shouldn't be rate limited.
    lastMessageTenSec = userJson["lastMessageTenSec"]
    lastMessageMinute = userJson["lastMessageMinute"]
    lastMessageTenSec = datetime.datetime.strptime(lastMessageTenSec, "%m/%d/%Y, %H:%M:%S")
    lastMessageMinute = datetime.datetime.strptime(lastMessageMinute, "%m/%d/%Y, %H:%M:%S")

    # Make sure the user hasn't sent more than 10 messages in a minute.
    if currTime >= lastMessageMinute + datetime.timedelta(minutes=1):
        userJson["lastMessageTenSec"] = currTimeStr
        userJson["lastMessageMinute"] = currTimeStr
        userJson["numMessagesInTenSec"] = 1
        userJson["numMessagesInMinute"] = 1
        return False
    else:
        userJson["numMessagesInMinute"] += 1
        if userJson["numMessagesInMinute"] > 10:
            await message.channel.send(f"{message.author.mention}: You are sending too many messages at once. Please wait a bit and try again.")
            return True
        
        if currTime >= lastMessageTenSec + datetime.timedelta(seconds=10):
            userJson["lastMessageTenSec"] = currTimeStr
            userJson["numMessagesInTenSec"] = 1
            return False
        else:
            userJson["numMessagesInTenSec"] += 1
            if userJson["numMessagesInTenSec"] > 2:
                await message.channel.send(f"{message.author.mention}: You are sending too many messages at once. Please wait a bit and try again.")
                return True

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # Creates the userfile if necessary.
    messageAuthor = str(message.author).strip("<>:\"/\\|?*")
    if not os.path.isfile(f"users/{messageAuthor}.json"):
        userFile = open(f"users/{messageAuthor}.json", 'w')
        userFile.write("{}")
        userFile.close()

    # Makes sure the user isn't sending too many messages.
    if message.content.startswith("$"):
        # Gets the data for the user.
        with open(f"users/{messageAuthor}.json", 'r') as userFile:
            userJson = json.load(userFile)

        rateLimited = await rateLimit(message, userJson)

        # Saves the rate limit data to the user's JSON file.
        with open(f"users/{messageAuthor}.json", 'w') as userFile:
            json.dump(userJson, userFile)

        if rateLimited:
            return

    if message.content.startswith('$hello'):
        await message.channel.send('Greetings from the Chain Estate DAO bot!')

    if message.content.startswith('$getChannelId'):
        await message.channel.send(message.channel.id)

    # Command to set the contract address, time between stat generations, time between stat messages, and the channel ID to message
    if message.content.startswith('$setConfig'):
        if str(message.author) not in adminUsers:
            await message.channel.send("Only Chain Estate DAO admins can use this command.")
        else:
            await setConfig(message)

    if message.content.startswith('resetStats'):
        if str(message.author) not in adminUsers:
            await message.channel.send("Only Chain Estate DAO admins can use this command.")
        else:
            await resetStats(message)

    if message.content.startswith('$message-stats'):
        if str(message.author) not in adminUsers:
            await message.channel.send("Only Chain Estate DAO admins can use this command.")
        else:
            await callMessageTokenStatistics(client)


client.run(os.environ["ChainEstateBotToken"])