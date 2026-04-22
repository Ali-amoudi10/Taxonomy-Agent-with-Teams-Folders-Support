PLEASE READ EVERYTHING IN THIS FILE

Steps to install the required dependencies (libraries and packages):
1. First you need to install python on your device.
    To do this you can go to Microsoft Store app and type "Python" in the search bar.
    The search result will show several Python versions. Download the one that says Python 3.13
2. Double click on run_toxonomy_agent.bat
    If this is the first time you are running this application, it might take some time to insatll the requirements.
    Once the requirements are installed it may show a configuration window. You should see three options on the top of the window. Press on "Import .env file".
    Another pop up window will apear to choose a file.
    Go to the directory of this folder and choose the file ".env" then press "Save and Launch".
    This setup will happen only the first time you run the app.

Steps to run and use the app:
1. Double click on run_toxonomy_agent.bat (If this is the first time then refer to previouse section "Steps to install the required dependencies")
2. To use the agent you can type a message in the bottom left chat bar and click send.
Anyway, it won't retrieve any slides unless you set a directory.
To do this you can click on "Browse" button on the top right corner (under settings) or paste the path of the directory you want to search.
Once the directory is chosen, an indexing bar will appear in the bottom left just under the chat.
It might have to download some of the files from the cloud to be able to read the content and create the database (Not very efficient but this is what we have now).
3. Once the directory is indexed successfully, you can ask the agent to retrieve the slides you need.
4. Once the agent retrieves the slides, it gives an overview of the found slides in the "Suggested Slides" section.
5. You can press "Add" on the slides that you like and they will be added to the "Deck Builder" where you can rearange them as you like and then press "Export Deck" to save the selected slides as a temporary power point file.
To change the saving preferences you can go to the settings in the top right corner and choose whether you want it to always save to the same directory or ask you each time.

Very Important Note:
So far, we can't access teams folders using the agent. That's why in order to use the agent for finding the slides in a certain teams folder you will have to follow these steps:
1. Go to the folder that contains the presentations on teams and find the three dots symbol (...).
2. Click on the three dots and press on "Sync". It might ask you to give it permission to use OneDrive and start syncronization. Accept it and wait until it does the syncronization.
3. On your device, go to "File Explorer" and go to the left bar that shows different directories.
If you go to bottom of this bar you should find three options:
Capgemini
This PC
Network
Go to Capgemini and check if the teams folder is syncronized on your device. If it is there, then you can just use this directory with your agent. If it's not then just wait until syncronization is finished then try again.