/**
 * Helpers.gs
 * Utility functions for formatting and calculations.
 */

/**
 * Normalizes name formatting to Title Case.
 */
function toTitleCase(str) {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
}

/**
 * Assigns athletes to their respective teams based on TEAMS config.
 */
function getTeam(firstName) {
  const name = toTitleCase(firstName);
  for (const [teamName, members] of Object.entries(TEAMS)) {
    if (members.map(m => m.toLowerCase()).includes(name.toLowerCase())) {
      return teamName;
    }
  }
  return 'Other';
}

/**
 * Gets the multiplier for an activity, with special rules for certain athletes.
 */
function getMultiplier(type, name, pace) {
  if (SPECIAL_MULTIPLIERS[name] && SPECIAL_MULTIPLIERS[name][type]) {
    const rule = SPECIAL_MULTIPLIERS[name][type];
    if (pace > rule.threshold) {
      return rule.multiplier;
    }
  }
  return MULTIPLIERS[type] || 0.0;
}

/**
 * Calculates weighted distance based on the activity type multiplier.
 */
function getEffectiveDistance(distKm, type, name, pace) {
  const multiplier = getMultiplier(type, name, pace);
  return Number((distKm * multiplier).toFixed(2));
}

/**
 * Formats duration in minutes to mm:ss or hh:mm:ss string.
 */
function formatDuration(decimalMinutes) {
  if (!decimalMinutes || decimalMinutes === 0) return '0:00';
  const totalSeconds = Math.round(decimalMinutes * 60);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  let result = '';
  if (hours > 0) result += hours + ':';
  result += (hours > 0 ? minutes.toString().padStart(2, '0') : minutes) + ':';
  result += seconds.toString().padStart(2, '0');
  return result;
}

/**
 * Calculates cumulative statistics for athletes and teams.
 */
function calculateStats() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Data');
  const data = sheet.getDataRange().getValues();
  const rows = data.slice(1);

  const athleteStats = {};
  const teamStats = {};

  rows.forEach(row => {
    const name = row[1];
    const team = row[2];
    const effDist = Number(row[5]) || 0;

    if (!athleteStats[name]) {
      athleteStats[name] = { totalEffort: 0, activities: 0, team: team };
    }
    athleteStats[name].totalEffort += effDist;
    athleteStats[name].activities += 1;

    if (!teamStats[team]) {
      teamStats[team] = { totalEffort: 0 };
    }
    teamStats[team].totalEffort += effDist;
  });

  return { athleteStats, teamStats };
}
