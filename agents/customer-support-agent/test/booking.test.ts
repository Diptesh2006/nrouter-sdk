import { describe, it, expect } from 'vitest';
import { matchesBookingIntent } from '../src/booking.js';

describe('matchesBookingIntent', () => {
  it.each([
    'Can I book a meeting?',
    'I want to book a call with you',
    'book a demo please',
    'How do I schedule a call?',
    'Schedule a demo for next week',
    'schedule a meeting',
    'I need to talk to sales',
    'can I talk to a human',
    'Let me talk to a person',
    'I want to talk to someone about this',
    'Can I speak to sales?',
    'speak with someone',
    'I would like to speak with a person',
    'How do I get a demo?',
    'I want to request a demo',
    'Please contact sales for me',
    'What is your enterprise pricing?',
    'Tell me about the enterprise plan',
    'We need an enterprise contract',
    'Is there an enterprise agreement?',
    'Do you offer custom pricing?',
    'Is there a volume discount?',
    'Our procurement team has questions',
    'We need a security review first',
    'Do you offer an SLA?',
    'what is the sla on uptime',
  ])('matches %j', (message) => {
    expect(matchesBookingIntent(message)).toBe(true);
  });

  it('is case-insensitive and tolerates extra whitespace', () => {
    expect(matchesBookingIntent('BOOK A   DEMO')).toBe(true);
    expect(matchesBookingIntent('Talk\n to   Sales')).toBe(true);
  });

  it.each([
    'is the demo key rate limited?',
    'how do I call the API?',
    'human-readable errors',
    'human',
    'call',
    'demo',
    'enterprise',
    'pricing',
    'What does pricing look like for the demo call?',
    'Is the enterprise tier human reviewed?',
    'How do I translate text?',
    'why is my balance negative',
    '',
  ])('does not match %j', (message) => {
    expect(matchesBookingIntent(message)).toBe(false);
  });

  it('never matches a non-string', () => {
    expect(matchesBookingIntent(undefined as unknown as string)).toBe(false);
    expect(matchesBookingIntent(42 as unknown as string)).toBe(false);
  });

  it('only scans a bounded prefix of a very long message', () => {
    expect(matchesBookingIntent('x'.repeat(100_000) + ' contact sales')).toBe(false);
    expect(matchesBookingIntent('contact sales ' + 'x'.repeat(100_000))).toBe(true);
  });
});
