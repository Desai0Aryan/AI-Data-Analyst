/** Plays queued items one at a time with a per-item delay.
 *  Demo/replay backends answer in milliseconds; the pacer lets people actually *watch* each stage.
 *  The first item is handled immediately; each later item waits for the previous item's delay. */
export class Pacer<T> {
  private queue: T[] = [];
  private timer: ReturnType<typeof setTimeout> | null = null;
  private idleWaiters: Array<() => void> = [];

  constructor(private handle: (item: T) => void, private delayFor: (item: T) => number) {}

  push(item: T) {
    this.queue.push(item);
    if (this.timer === null) this.next();
  }

  private next() {
    const item = this.queue.shift();
    if (item === undefined) {
      this.timer = null;
      this.idleWaiters.splice(0).forEach((resolve) => resolve());
      return;
    }
    this.handle(item);
    this.timer = setTimeout(() => {
      this.timer = null;
      this.next();
    }, this.delayFor(item));
  }

  /** Resolves once everything queued so far has been handled and its delay has elapsed. */
  idle(): Promise<void> {
    if (this.queue.length === 0 && this.timer === null) return Promise.resolve();
    return new Promise((resolve) => this.idleWaiters.push(resolve));
  }

  clear() {
    this.queue = [];
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.idleWaiters.splice(0).forEach((resolve) => resolve());
  }
}
