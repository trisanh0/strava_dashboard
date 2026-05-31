/**
 * Main.gs
 * Core logic for fetching activities and sending notifications.
 */

/**
 * Main routine: Fetches, filters, and logs new activities.
 */
function fetchClubActivities() {
    const service = getStravaService();
    if (!service.hasAccess()) {
        Logger.log('Authentication lost. Run logAuthUrl().');
        return;
    }

    const url = `https://www.strava.com/api/v3/clubs/${CLUB_ID}/activities?per_page=200`;
    let activities;

    try {
        const response = UrlFetchApp.fetch(url, {
            headers: { Authorization: `Bearer ${service.getAccessToken()}` }
        });
        activities = JSON.parse(response.getContentText());
    } catch (e) {
        Logger.log(`Fetch error: ${e.message}`);
        return;
    }

    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName('Data');
    const lastRow = sheet.getLastRow();
    const existingIds = lastRow > 1
        ? sheet.getRange(2, 1, lastRow - 1, 1).getValues().flat().map(String)
        : [];

    const newRows = activities
        .map(act => {
            const athleteKey = `${act.athlete.firstname}_${act.athlete.lastname}`.replace(/\s+/g, '_');
            const uniqueId = `${athleteKey}_${act.distance}_${act.moving_time}_${act.name}`.replace(/\s+/g, '_');

            if (existingIds.includes(uniqueId)) return null;

            const dateStr = act.start_date_local || act.start_date;
            const date = dateStr ? new Date(dateStr) : new Date();
            const distKm = (act.distance || 0) / 1000;
            const durationMin = (act.moving_time || 0) / 60;
            const paceDecimal = distKm > 0 ? Number((durationMin / distKm).toFixed(2)) : 0;
            const firstName = toTitleCase(act.athlete.firstname);
            const team = getTeam(firstName);
            const effectiveDistKm = getEffectiveDistance(distKm, act.type, firstName, paceDecimal);

            return [
                uniqueId, firstName, team, date,
                Number(distKm.toFixed(2)), effectiveDistKm,
                Number(durationMin.toFixed(2)), paceDecimal,
                act.total_elevation_gain || 0, act.type
            ];
        })
        .filter(row => row !== null);

    if (newRows.length > 0) {
        sheet.getRange(lastRow + 1, 1, newRows.length, newRows[0].length).setValues(newRows);
        Logger.log(`Added ${newRows.length} items.`);
        sendDiscordNotification(newRows);
    } else {
        Logger.log('No new activities found.');
    }
}

/**
 * Sends a formatted notification to Discord for new activities.
 */
function sendDiscordNotification(newActivities) {
    if (!DISCORD_WEBHOOK_URL) {
        Logger.log('DISCORD_WEBHOOK_URL not set. Skipping notification.');
        return;
    }

    const filteredActivities = newActivities.filter(act => {
        const dist = act[4];
        const type = act[9];
        return type !== 'Walk' || dist > 1.0;
    });

    if (filteredActivities.length === 0) {
        Logger.log('No qualifying activities for Discord notification.');
        return;
    }

    const embeds = filteredActivities.map(act => {
        const [id, name, team, date, dist, effDist, duration, pace, elevation, type] = act;
        const multiplier = getMultiplier(type, name, pace);

        return {
            color: DISCORD_COLOR,
            fields: [
                { name: 'Distance', value: `${dist.toFixed(2)} km`, inline: true },
                { name: 'Multiplier', value: `${multiplier.toFixed(2)}x`, inline: true },
                { name: 'Effort', value: `${effDist.toFixed(2)}`, inline: true },
                { name: 'Duration', value: `${duration.toFixed(2)} min`, inline: true },
                { name: 'Pace', value: `${formatDuration(pace)}/km`, inline: true },
                { name: 'Elevation', value: `${elevation} m`, inline: true },
                { name: 'Team', value: team, inline: true },
            ],
            timestamp: new Date(date).toISOString()
        };
    });

    for (let i = 0; i < filteredActivities.length; i++) {
        const act = filteredActivities[i];
        const name = act[1];
        const type = act[9];
        
        const discordId = DISCORD_IDS[name];
        const mention = (discordId && discordId !== '') ? `<@${discordId}>` : name;

        const randomMessage = DISCORD_PHRASES[Math.floor(Math.random() * DISCORD_PHRASES.length)]
            .replace('{name}', mention)
            .replace('{type}', type);

        const payload = {
            content: randomMessage,
            embeds: [embeds[i]]
        };

        const options = {
            method: 'post',
            contentType: 'application/json',
            payload: JSON.stringify(payload),
            muteHttpExceptions: true
        };

        let success = false;
        let retries = 0;
        const maxRetries = 3;

        while (!success && retries <= maxRetries) {
            try {
                const response = UrlFetchApp.fetch(DISCORD_WEBHOOK_URL, options);
                const responseCode = response.getResponseCode();

                if (responseCode >= 200 && responseCode < 300) {
                    success = true;
                    Utilities.sleep(1000); // Standard delay between requests
                } else if (responseCode === 429) {
                    let waitTime = 2000; // Default wait time if header is missing
                    const headers = response.getHeaders();
                    
                    try {
                        const body = JSON.parse(response.getContentText());
                        if (body.retry_after) {
                            // Discord sometimes returns seconds (3.17) and sometimes ms (3170)
                            waitTime = body.retry_after < 1000 ? body.retry_after * 1000 : body.retry_after;
                        }
                    } catch (e) {
                        // Fallback to headers
                        const retryAfterHeader = headers['Retry-After'] || headers['retry-after'];
                        if (retryAfterHeader) {
                            const val = parseFloat(retryAfterHeader);
                            waitTime = val < 100 ? val * 1000 : val; 
                        }
                    }
                    
                    waitTime = Math.round(waitTime + 500); // Add 500ms buffer
                    if (waitTime > 15000) waitTime = 15000; // Cap at 15s to avoid GAS execution limits
                    
                    Logger.log(`Rate limited (429). Retrying in ${waitTime}ms... (Attempt ${retries + 1}/${maxRetries + 1})`);
                    Utilities.sleep(waitTime);
                    retries++;
                } else {
                    Logger.log(`Unexpected Discord error: ${responseCode} - ${response.getContentText()}`);
                    break; // Break on other HTTP errors (400, 401, etc.)
                }
            } catch (e) {
                Logger.log(`Fetch error during Discord notification: ${e.message}`);
                Utilities.sleep(2000 * (retries + 1)); // Backoff on network errors
                retries++;
            }
        }
        
        if (!success) {
            Logger.log(`Failed to send notification for ${name} after multiple attempts.`);
        }
    }
    Logger.log(`Finished processing Discord notifications.`);
}
