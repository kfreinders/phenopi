import { describe, expect, it } from "vitest";
import { buildCaptureProgress } from "./SchedulerPage";

const capture = (time, replicate, status) => ({
  time,
  scheduled_at: `2026-07-23T${time}+02:00`,
  replicate,
  status,
  message: null,
});

describe("daily capture progress", () => {
  it("stops the pulse at the unfinished replicate instead of the next time point", () => {
    const progress = {
      points: [
        { captures: [capture("16:51:00", 1, "succeeded"), capture("16:51:30", 2, "succeeded")] },
        { captures: [capture("16:52:00", 1, "succeeded"), capture("16:52:30", 2, "remaining")] },
        { captures: [capture("16:53:00", 1, "remaining"), capture("16:53:30", 2, "remaining")] },
      ],
    };

    const result = buildCaptureProgress(progress);

    expect(result.next.time).toBe("16:52:30");
    expect(result.next.replicate).toBe(2);
    expect(result.next.percent).toBeCloseTo(50);
    expect(result.completedWidth).toBeCloseTo(0);
    expect(result.pulseStart).toBeCloseTo(0);
    expect(result.pulseWidth).toBeCloseTo(50);
  });

  it("keeps replicates grouped at their primary time point", () => {
    const progress = {
      points: [
        { captures: [capture("16:05:00", 1, "succeeded"), capture("16:05:30", 2, "remaining")] },
        { captures: [capture("16:06:00", 1, "remaining"), capture("16:06:30", 2, "remaining")] },
      ],
    };

    const result = buildCaptureProgress(progress);

    expect(result.points).toHaveLength(2);
    expect(result.points[0].captures).toHaveLength(2);
    expect(result.points[0].captures[1].replicate).toBe(2);
    expect(result.next.time).toBe("16:05:30");
    expect(result.next.percent).toBe(0);
  });
});
