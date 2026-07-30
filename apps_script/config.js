/**
 * Config.gs
 * Project constants and property retrieval.
 */

const props = PropertiesService.getScriptProperties();
const CLIENT_ID = props.getProperty('CLIENT_ID');
const CLIENT_SECRET = props.getProperty('CLIENT_SECRET');
const CLUB_ID = props.getProperty('CLUB_ID');
const DISCORD_WEBHOOK_URL = props.getProperty('DISCORD_WEBHOOK_URL');

const DISCORD_IDS = {
  'Srikar': '258466487012950018',
  'Wilco': '295065586797510658',
  'Trisan': '481967966657839107',
  'Jared': '273345887550439425',
  'Raymond': '581670531284074496',
  'Minnie': '608938431720194069',
  'Grace': '975644415852957736',
  'Chaomin': '608938431720194069',
  'Ravi': '328750094016970752',
  'Andy': '529931472233168908',
  'Scott': '635006091734024192',
  'Ben': '326226967160553472',
  'Tommy': '251433215481348096',
  'Jinchien': '423613231974842378'
};

const TEAMS = {
  'Srikar': ['Srikar', 'Wilco', 'Trisan', 'Jared', 'Raymond', "Minnie", "Jinchien"],
  'Ravi': ['Ravi', 'Andy', 'Scott', 'Ben', 'Tommy']
};

const MULTIPLIERS = {
  'Hike': 0.5,
  'Ride': 0.3,
  'Rowing': 0.75,
  'Run': 1.0,
  'Swim': 4.0,
  'Walk': 0.2,
  'Workout': 0.3
};

// Special rules that apply to specific athletes based on activity details (e.g. pace)
const SPECIAL_MULTIPLIERS = {
  'Srikar': {
    'Run': {
      threshold: 9.0, // pace > 9.0
      multiplier: 0.6
    }
  }
};

const DISCORD_COLOR = 15548997; // Strava-esque Orange/Red

const DISCORD_PHRASES = [
  "{name} completed a {type}!",
  "{name} just completed a {type}!",
  "{name} conquered a {type}!",
  "{name} powered through a {type}!",
  "{name} triumphantly completed a {type}!",
  "{name} mastered a {type}!",
  "{name} soared through a {type}!",
  "{name} crushed a {type}!",
  "{name} courageously conquered a {type}!",
  "{name} absolutely destroyed a {type}!",
  "{name} sailed through a {type}!",
  "{name} magnificently finished a {type}!",
  "{name} casually knocked out a {type}!",
  "{name} dominated a {type}!",
  "{name} supercharged their day with a {type}!",
  "{name} excelled in a {type}!",
  "{name} brought their A-game to a {type}!",
  "{name} impressed everyone during a {type}!",
  "{name} delivered a legendary {type}!",
  "{name} inspired the team with a {type}!",
  "{name} amazed everyone with a {type}!",
  "{name} smiled their way through a {type}!",
  "{name} stormed across the finish line of a {type}!",
  "{name} had a fantastic time on a {type}!",
  "{name} is feeling stronger than ever after that {type}!",
  "Legend has it {name} just set the standard with that {type}!",
  "Hats off to {name} for completing a {type}!",
  "Everyone give it up for the incredible {type} that {name} just did!",
  "Give a huge round of applause for {name}, who just completed a {type}!",
  "{name} successfully completed a {type} with flying colors!",
  "The prophecy has been fulfilled: {name} achieved greatness in a {type}!",
  "With pure determination, {name} finished a {type} today!"
];

const SRIKAR_DISCORD_PHRASES = [
  "{name} somehow waddled through a {type}! AUT degree clearly putting in work.",
  "{name} finished a {type}! Time to celebrate with another fatass meal.",
  "{name} attempted a {type}. Still won't get you into UoA or the U24 team though.",
  "Miracle of the day: {name} survived a {type} instead of playing games with Jared.",
  "{name} logged a {type}! Almost as embarrassing as his golf game.",
  "{name} completed a {type}! Wilco is still better at frisbee though.",
  "{name} dragged himself through a {type}! Back to AUT lectures you go.",
  "{name} actually did a {type}! Did Jared cheer you on the whole time?",
  "{name} finished a {type}! Still can't hit a golf ball straight to save his life."
];

