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
  'Tommy': '251433215481348096'
};

const TEAMS = {
  'Srikar': ['Srikar', 'Wilco', 'Trisan', 'Jared', 'Raymond', "Minnie", "Grace", "Chaomin"],
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

const DISCORD_COLOR = 15548997; // Strava-esque Orange/Red

const DISCORD_PHRASES = [
  "{name} completed a {type}!",
  "{name} just completed a {type}!",
  "{name} attempted a {type}!",
  "{name} tried to {type}!",
  "{name} somehow completed a {type}!",
  "{name} survived a {type}!",
  "{name} suffered through a {type}!",
  "{name} crushed a {type}!",
  "{name} bravely faced a {type}!",
  "{name} absolutely destroyed a {type}!",
  "{name} stumbled through a {type}!",
  "{name} miraculously finished a {type}!",
  "{name} casually knocked out a {type}!",
  "{name} actually did a {type}!",
  "{name} barely survived a {type}!",
  "{name} endured a {type}!",
  "{name} pretended to do a {type}!",
  "{name} embarrassed themselves during a {type}!",
  "{name} calls this a {type}? Yikes.",
  "{name} disgraced the team with a {type}!",
  "{name} disappointed everyone with a {type}!",
  "{name} cried their way through a {type}!",
  "{name} crawled across the finish line of a {type}!",
  "{name} had a miserable time on a {type}!",
  "{name} is still recovering from that {type}.",
  "Rumour has it {name} only did that {type} for the Discord notification.",
  "Wait, {name} did a {type}? Are they okay?",
  "Everyone pretend to be impressed by the {type} that {name} just did.",
  "Please clap for {name}, who just completed a {type}.",
  "{name} successfully completed a {type} – this time, without passing out.",
  "The prophecy has been fulfilled: {name} did a {type}.",
  "Against all odds, {name} finished a {type} today."
];
