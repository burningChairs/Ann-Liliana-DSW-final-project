from flask import Flask, redirect, url_for, session, request, jsonify, render_template, flash
from markupsafe import Markup
from flask_oauthlib.client import OAuth
from bson.objectid import ObjectId
from datetime import datetime, timedelta

import pprint
import os
import random
import pymongo
import sys
import datetime
 
app = Flask(__name__)

app.debug = False #Change this to False for production
#os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' #Remove once done debugging

app.secret_key = os.environ['SECRET_KEY'] #used to sign session cookies
oauth = OAuth(app)
oauth.init_app(app) #initialize the app to be able to make requests for user information

#Set up GitHub as OAuth provider
github = oauth.remote_app(
    'github',
    consumer_key=os.environ['GITHUB_CLIENT_ID'], #your web app's "username" for github's OAuth
    consumer_secret=os.environ['GITHUB_CLIENT_SECRET'],#your web app's "password" for github's OAuth
    request_token_params={'scope': 'user:email'}, #request read-only access to the user's email.  For a list of possible scopes, see developer.github.com/apps/building-oauth-apps/scopes-for-oauth-apps
    base_url='https://api.github.com/',
    request_token_url=None,
    access_token_method='POST',
    access_token_url='https://github.com/login/oauth/access_token',  
    authorize_url='https://github.com/login/oauth/authorize' #URL for github's OAuth login
)

#Connect to database
url = os.environ["MONGO_CONNECTION_STRING"]
client = pymongo.MongoClient(url)
db = client[os.environ["MONGO_DBNAME"]]
collection = db['userinfo'] #TODO: put the name of the collection here

# Send a ping to confirm a successful connection
try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)
    
@app.route('/api/can_play')
def can_play():
    if not ('github_token' in session):
        return jsonify({'can_play': False, 'reason': 'not_logged_in'})
    user_id = session['user_data']['id']
    user_doc = collection.find_one({'user_id': user_id})
    now = datetime.utcnow()
    if user_doc and 'last_play' in user_doc:
        last_play = datetime.fromisoformat(user_doc['last_play'])
        if now < last_play + timedelta(minutes=5):
            time_left = (last_play + timedelta(minutes=5) - now).seconds #5 minutes for now
            return jsonify({'can_play': False, 'reason': 'cooldown', 'seconds_left': time_left})
    return jsonify({'can_play': True})

@app.route('/page1', methods=['GET', 'POST'])
def renderPage1():
    if ('github_token' not in session):
        return redirect(url_for('login'))
     
    if 'secret_number' not in session:
        session['secret_number'] = random.randint(0, 99)
        session['guesses_made'] = 0
        session['guess_history'] = []
    message = session.get('game_message', '')
    history = session.get('guess_history', [])
    guesses_made = session.get('guesses_made', 0)
    guesses_left = 6 - guesses_made    
    
    if request.method == 'POST' and guesses_left > 0:
        try:
            user_guess = int(request.form.get('user_input'))
        except (TypeError, ValueError):
            session['game_message'] = 'Invalid input. Try again'
            message = session['game_message']
            return render_template('page1.html', message=message, history=history, guesses_left=guesses_left)
    
        guesses_made += 1
        session['guesses_made'] = guesses_made
        guesses_left = 6 - guesses_made
        
        secret_number = session['secret_number']
        history.append(f'You guessed {user_guess}')
        session['guess_history'] = history
        
        if user_guess == secret_number:
            session['game_message'] = f'CORRECT The number was {secret_number}. Game over'
            user_id = session['user_data']['id']
            username = session['user_data']['login']
            collection.update_one(
                {'user_id': user_id},
                {
                    '$set': {
                        'last_play': datetime.datetime.utcnow().isoformat(),
                        'username': username
                    }
                },
                upsert=True
            )
        elif guesses_made >= 6:
            session['game_message'] = f'GAME OVER The number was {secret_number}. Game over'
        elif user_guess < secret_number: #for now till we can change it to color variation rather that too close or too high
            session['game_message'] = 'Too low'
        else:
            session['game_message'] = 'Too high'
        message = session['game_message']
        
    return render_template('page1.html', message=message, history=history, guesses_left=guesses_left)
        
#def get_minute_specific_number(lower_bound, upper_bound):
    #"""
    #Generates a consistent number for the current minute using the minute 
    #of the hour as the random seed.
    #"""
    # 1. Get the current time.
    #now = datetime.datetime.now()
    
    # 2. Extract the current minute (an integer between 0 and 59).
    #current_minute = now.minute
    
    # 3. Use the minute as the seed for the random number generator.
    # Seeding ensures the number generated is the same for the entire minute.
    #random.seed(current_minute)
    
    # 4. Generate the "random" number within the specified range.
    # Use randint for inclusive range.
    #result = random.randint(lower_bound, upper_bound)
    
    #return result

## Generate a number between 1 and 100 that is the same for the current minute.
#number = get_minute_specific_number(1, 100)
#print(f"The consistent number for this minute is: {number}")


#context processors run before templates are rendered and add variable(s) to the template's context
#context processors must return a dictionary 
#this context processor adds the variable logged_in to the conext for all templates
@app.context_processor
def inject_logged_in():
    return {"logged_in":('github_token' in session)}

@app.route('/')
def home():
    return render_template('home.html')

#redirect to GitHub's OAuth page and confirm callback URL
@app.route('/login')
def login():   
    return github.authorize(callback=url_for('authorized', _external=True, _scheme='http')) #callback URL must match the pre-configured callback URL

@app.route('/logout')
def logout():
    session.clear()
    flash('You were logged out.')
    return redirect('/')

@app.route('/login/authorized')
def authorized():
    resp = github.authorized_response()
    if resp is None:
        session.clear()
        flash('Access denied: reason=' + request.args['error'] + ' error=' + request.args['error_description'] + ' full=' + pprint.pformat(request.args), 'error')      
    else:
        try:
            session['github_token'] = (resp['access_token'], '') #save the token to prove that the user logged in
            session['user_data']=github.get('user').data
            message = 'You were successfully logged in as ' + session['user_data']['login'] + '.'
        except Exception as inst:
            session.clear()
            print(inst)
            message = 'Unable to login, please try again.', 'error'
    return render_template('message.html', message=message)


#@app.route('/page1')
#def renderPage1():
#    return render_template('page1.html')

@app.route('/page2')
def renderPage2():
    return render_template('page2.html')
 
@app.route('/update_p')
def update():
    return Markup("<p>This text came from the server.</p>")
    
    
    
#the tokengetter is automatically called to check who is logged in.
@github.tokengetter
def get_github_oauth_token():
    return session['github_token']


if __name__ == '__main__':
    app.run()
