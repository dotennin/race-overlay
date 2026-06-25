import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { readTcx } from "./tcx";

describe("readTcx", () => {
  it("reads the checked-in TCX fixture into the browser activity model", () => {
    const xml = readFileSync(resolve("..", "tests", "fixtures", "sample_activity.tcx"), "utf8");

    const activity = readTcx(xml);

    expect(activity.sport).toBe("Running");
    expect(activity.laps).toEqual([]);
    expect(activity.samples).toHaveLength(3);
    expect(activity.samples[0]).toMatchObject({
      timestamp: "2026-04-19T00:45:05.000Z",
      latitude: 36.0832622554,
      longitude: 140.2106574643,
      altitudeM: -1.4,
      distanceM: 2.9,
      speedMps: 1.521,
      heartRateBpm: 103,
      cadenceSpm: 0,
    });
  });

  it("normalizes running RunCadence to steps per minute", () => {
    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap StartTime="2026-04-19T00:45:05Z">
        <Track>
          <Trackpoint>
            <Time>2026-04-19T00:45:05Z</Time>
            <Extensions><ns3:TPX><ns3:RunCadence>92</ns3:RunCadence></ns3:TPX></Extensions>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>`;

    const activity = readTcx(xml);

    expect(activity.samples[0].cadenceSpm).toBe(184);
  });

  it("reads heart-rate values from the correct TCX parent elements", () => {
    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap StartTime="2026-04-19T00:45:00Z">
        <AverageHeartRateBpm><Value>111</Value></AverageHeartRateBpm>
        <MaximumHeartRateBpm><Value>144</Value></MaximumHeartRateBpm>
        <Track>
          <Trackpoint>
            <Time>2026-04-19T00:45:00Z</Time>
            <DistanceMeters>0</DistanceMeters>
            <Extensions><ns3:TPX><ns3:Watts><Value>250</Value></ns3:Watts></ns3:TPX></Extensions>
            <HeartRateBpm><Value>101</Value></HeartRateBpm>
            <Extensions><ns3:TPX><ns3:Speed>3</ns3:Speed></ns3:TPX></Extensions>
          </Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>`;

    const activity = readTcx(xml);

    expect(activity.samples[0].heartRateBpm).toBe(101);
    expect(activity.laps[0].avgHeartRateBpm).toBe(111);
    expect(activity.laps[0].maxHeartRateBpm).toBe(144);
  });

  it("derives lap distance from trackpoint deltas when lap summary distance is absent", () => {
    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
  <Activities>
    <Activity Sport="Running">
      <Lap StartTime="2026-04-19T00:45:00Z">
        <Track>
          <Trackpoint><Time>2026-04-19T00:45:00Z</Time><DistanceMeters>1000</DistanceMeters></Trackpoint>
          <Trackpoint><Time>2026-04-19T00:47:00Z</Time><DistanceMeters>1900</DistanceMeters></Trackpoint>
        </Track>
      </Lap>
    </Activity>
  </Activities>
</TrainingCenterDatabase>`;

    const activity = readTcx(xml);

    expect(activity.laps[0].distanceM).toBe(900);
  });
});
