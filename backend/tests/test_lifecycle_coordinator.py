"""Tests for lifecycle coordinator."""

import signal
import threading
import time
from unittest.mock import MagicMock, patch

from app.utils.lifecycle_coordinator import LifecycleCoordinator, LifecycleEvent
from tests.testing_utils import TestLifecycleCoordinator


class TestProductionLifecycleCoordinator:
    """Test lifecycle coordinator functionality."""

    def test_lifecycle_event_sequence(self):
        """Test that LifecycleEvent notifications are sent in correct order."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        # Track the order of events
        events_received = []

        def notification_callback(event: LifecycleEvent):
            events_received.append(event)

        coordinator.register_lifecycle_notification(notification_callback)

        # Trigger shutdown
        coordinator._handle_sigterm(signal.SIGTERM, None)

        # Should receive both events in order
        assert len(events_received) == 3
        assert events_received[0] == LifecycleEvent.PREPARE_SHUTDOWN
        assert events_received[1] == LifecycleEvent.SHUTDOWN
        assert events_received[2] == LifecycleEvent.AFTER_SHUTDOWN

    def test_multiple_notifications(self):
        """Test multiple notification callbacks are called."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        callback1 = MagicMock()
        callback2 = MagicMock()
        callback3 = MagicMock()

        coordinator.register_lifecycle_notification(callback1)
        coordinator.register_lifecycle_notification(callback2)
        coordinator.register_lifecycle_notification(callback3)

        # Trigger shutdown
        coordinator._handle_sigterm(signal.SIGTERM, None)

        # All callbacks should be called twice (PREPARE_SHUTDOWN + SHUTDOWN)
        assert callback1.call_count == 3
        assert callback2.call_count == 3
        assert callback3.call_count == 3

        # Check they were called with correct events
        callback1.assert_any_call(LifecycleEvent.PREPARE_SHUTDOWN)
        callback1.assert_any_call(LifecycleEvent.SHUTDOWN)
        callback1.assert_any_call(LifecycleEvent.AFTER_SHUTDOWN)

    def test_shutdown_waiters_sequential_execution(self):
        """Test that shutdown waiters are called sequentially with proper timeouts."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=5)

        after_shutdown_attempted = False

        def lifecycle_notification(event: LifecycleEvent):
            nonlocal after_shutdown_attempted
            if event == LifecycleEvent.AFTER_SHUTDOWN:
                after_shutdown_attempted = True

        coordinator.register_lifecycle_notification(lifecycle_notification)

        # Track the order and timing of waiter calls
        waiter_calls = []

        def waiter1(timeout: float) -> bool:
            waiter_calls.append(('waiter1', timeout))
            time.sleep(1)  # Simulate some work
            return True

        def waiter2(timeout: float) -> bool:
            waiter_calls.append(('waiter2', timeout))
            time.sleep(0.5)  # Simulate less work
            return True

        coordinator.register_shutdown_waiter("Service1", waiter1)
        coordinator.register_shutdown_waiter("Service2", waiter2)

        # Trigger shutdown
        start_time = time.perf_counter()
        coordinator._handle_sigterm(signal.SIGTERM, None)
        end_time = time.perf_counter()

        # Both waiters should have been called
        assert len(waiter_calls) == 2
        assert waiter_calls[0][0] == 'waiter1'
        assert waiter_calls[1][0] == 'waiter2'

        # waiter2 should get less timeout than waiter1 (since waiter1 used 1 second)
        waiter1_timeout = waiter_calls[0][1]
        waiter2_timeout = waiter_calls[1][1]
        assert waiter2_timeout < waiter1_timeout

        # Total execution should be about 1.5 seconds (1 + 0.5)
        total_time = end_time - start_time
        assert 1.4 < total_time < 2.0  # Allow some tolerance

        assert after_shutdown_attempted

    def test_waiter_timeout_exceeded(self):
        """Test behavior when waiter timeout is exceeded."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=0.5)

        after_shutdown_attempted = False

        def lifecycle_notification(event: LifecycleEvent):
            nonlocal after_shutdown_attempted
            if event == LifecycleEvent.AFTER_SHUTDOWN:
                after_shutdown_attempted = True

        coordinator.register_lifecycle_notification(lifecycle_notification)

        def slow_waiter(timeout: float) -> bool:
            time.sleep(1.0)  # Takes longer than total timeout
            return True

        def fast_waiter(timeout: float) -> bool:
            return True

        coordinator.register_shutdown_waiter("SlowService", slow_waiter)
        coordinator.register_shutdown_waiter("FastService", fast_waiter)

        # Trigger shutdown
        start_time = time.perf_counter()
        coordinator._handle_sigterm(signal.SIGTERM, None)
        end_time = time.perf_counter()

        # Should complete quickly due to timeout
        total_time = end_time - start_time
        assert total_time < 1.1  # Should not wait for slow waiter (allow small tolerance)

        assert after_shutdown_attempted

    def test_waiter_returns_false(self):
        """Test behavior when waiter returns False (not ready)."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        after_shutdown_attempted = False

        def lifecycle_notification(event: LifecycleEvent):
            nonlocal after_shutdown_attempted
            if event == LifecycleEvent.AFTER_SHUTDOWN:
                after_shutdown_attempted = True

        coordinator.register_lifecycle_notification(lifecycle_notification)

        def not_ready_waiter(timeout: float) -> bool:
            return False

        def ready_waiter(timeout: float) -> bool:
            return True

        coordinator.register_shutdown_waiter("NotReadyService", not_ready_waiter)
        coordinator.register_shutdown_waiter("ReadyService", ready_waiter)

        # Trigger shutdown
        coordinator._handle_sigterm(signal.SIGTERM, None)

        # Should still complete shutdown even if one waiter is not ready
        assert after_shutdown_attempted

    def test_is_shutting_down_state(self):
        """Test shutdown state tracking."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        # Initially not shutting down
        assert not coordinator.is_shutting_down()

        # Start shutdown in background thread to avoid blocking
        def shutdown_thread():
            coordinator._handle_sigterm(signal.SIGTERM, None)

        # Set up notification to check state during shutdown
        shutdown_state_during_notification = []

        def check_state_callback(event: LifecycleEvent):
            shutdown_state_during_notification.append((event, coordinator.is_shutting_down()))

        coordinator.register_lifecycle_notification(check_state_callback)

        thread = threading.Thread(target=shutdown_thread)
        thread.start()
        thread.join(timeout=5)

        # Should be shutting down during both events
        assert len(shutdown_state_during_notification) == 3
        assert shutdown_state_during_notification[0] == (LifecycleEvent.PREPARE_SHUTDOWN, True)
        assert shutdown_state_during_notification[1] == (LifecycleEvent.SHUTDOWN, True)
        assert shutdown_state_during_notification[2] == (LifecycleEvent.AFTER_SHUTDOWN, True)

    def test_double_signal_handling(self):
        """Test that multiple signals are handled gracefully."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        callback = MagicMock()
        coordinator.register_lifecycle_notification(callback)

        # Send signal twice rapidly
        coordinator._handle_sigterm(signal.SIGTERM, None)

        # Second signal should be ignored (already shutting down)
        with patch.object(coordinator, '_shutting_down', True):
            coordinator._handle_sigterm(signal.SIGTERM, None)

        # Callback should only be called twice (once for each event in first signal)
        assert callback.call_count == 3

    def test_notification_exception_handling(self):
        """Test that exceptions in notification callbacks don't break shutdown."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        def bad_callback(event: LifecycleEvent):
            raise Exception("Test error")

        def good_callback(event: LifecycleEvent):
            good_callback.calls = getattr(good_callback, 'calls', [])
            good_callback.calls.append(event)

        coordinator.register_lifecycle_notification(bad_callback)
        coordinator.register_lifecycle_notification(good_callback)

        # Should not raise exception
        coordinator._handle_sigterm(signal.SIGTERM, None)

        # Good callback should still be called
        assert len(good_callback.calls) == 3
        assert good_callback.calls[0] == LifecycleEvent.PREPARE_SHUTDOWN
        assert good_callback.calls[1] == LifecycleEvent.SHUTDOWN
        assert good_callback.calls[2] == LifecycleEvent.AFTER_SHUTDOWN

    def test_waiter_exception_handling(self):
        """Test that exceptions in waiters don't prevent shutdown."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        after_shutdown_attempted = False

        def lifecycle_notification(event: LifecycleEvent):
            nonlocal after_shutdown_attempted
            if event == LifecycleEvent.AFTER_SHUTDOWN:
                after_shutdown_attempted = True

        coordinator.register_lifecycle_notification(lifecycle_notification)

        def bad_waiter(timeout: float) -> bool:
            raise Exception("Waiter error")

        good_waiter_called = threading.Event()

        def good_waiter(timeout: float) -> bool:
            good_waiter_called.set()
            return True

        coordinator.register_shutdown_waiter("BadService", bad_waiter)
        coordinator.register_shutdown_waiter("GoodService", good_waiter)

        # Should still complete shutdown
        coordinator._handle_sigterm(signal.SIGTERM, None)

        # Good waiter should have been called
        assert good_waiter_called.is_set()

        assert after_shutdown_attempted

    def test_thread_safety(self):
        """Test thread safety of lifecycle coordinator."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        after_shutdown_attempted = False

        def lifecycle_notification(event: LifecycleEvent):
            nonlocal after_shutdown_attempted
            if event == LifecycleEvent.AFTER_SHUTDOWN:
                after_shutdown_attempted = True

        coordinator.register_lifecycle_notification(lifecycle_notification)

        # Multiple threads checking shutdown state
        results = []

        def check_state():
            for _ in range(100):
                results.append(coordinator.is_shutting_down())
                time.sleep(0.001)

        # Start multiple checker threads
        threads = [threading.Thread(target=check_state) for _ in range(3)]
        for t in threads:
            t.start()

        # Trigger shutdown after a brief delay
        time.sleep(0.05)
        shutdown_thread = threading.Thread(
            target=lambda: coordinator._handle_sigterm(signal.SIGTERM, None)
        )
        shutdown_thread.start()

        # Wait for all threads
        shutdown_thread.join(timeout=5)
        for t in threads:
            t.join(timeout=5)

        # Should have mix of True/False values (some before, some during shutdown)
        assert False in results  # Some checks before shutdown
        assert True in results   # Some checks during/after shutdown
        assert after_shutdown_attempted


    def test_fire_startup_dispatches_event(self):
        """Test that fire_startup() dispatches STARTUP event to all registered callbacks."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        events_received: list[LifecycleEvent] = []

        def callback(event: LifecycleEvent) -> None:
            events_received.append(event)

        coordinator.register_lifecycle_notification(callback)
        coordinator.fire_startup()

        assert len(events_received) == 1
        assert events_received[0] == LifecycleEvent.STARTUP

    def test_fire_startup_idempotent(self):
        """Test that fire_startup() is idempotent -- second call is a no-op."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        call_count = 0

        def callback(event: LifecycleEvent) -> None:
            nonlocal call_count
            if event == LifecycleEvent.STARTUP:
                call_count += 1

        coordinator.register_lifecycle_notification(callback)

        coordinator.fire_startup()
        coordinator.fire_startup()  # Second call should be ignored

        assert call_count == 1

    def test_fire_startup_multiple_callbacks(self):
        """Test that fire_startup() dispatches to all registered callbacks."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        callback1 = MagicMock()
        callback2 = MagicMock()
        callback3 = MagicMock()

        coordinator.register_lifecycle_notification(callback1)
        coordinator.register_lifecycle_notification(callback2)
        coordinator.register_lifecycle_notification(callback3)

        coordinator.fire_startup()

        callback1.assert_called_once_with(LifecycleEvent.STARTUP)
        callback2.assert_called_once_with(LifecycleEvent.STARTUP)
        callback3.assert_called_once_with(LifecycleEvent.STARTUP)

    def test_fire_startup_exception_handling(self):
        """Test that exceptions in STARTUP callbacks don't prevent other callbacks."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        def bad_callback(event: LifecycleEvent) -> None:
            raise Exception("Startup error")

        good_events: list[LifecycleEvent] = []

        def good_callback(event: LifecycleEvent) -> None:
            good_events.append(event)

        coordinator.register_lifecycle_notification(bad_callback)
        coordinator.register_lifecycle_notification(good_callback)

        # Should not raise
        coordinator.fire_startup()

        # Good callback should still be called
        assert len(good_events) == 1
        assert good_events[0] == LifecycleEvent.STARTUP

    def test_full_lifecycle_with_startup(self):
        """Test complete lifecycle: STARTUP -> PREPARE_SHUTDOWN -> waiters -> SHUTDOWN -> AFTER_SHUTDOWN."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        events_received: list[LifecycleEvent] = []

        def callback(event: LifecycleEvent) -> None:
            events_received.append(event)

        coordinator.register_lifecycle_notification(callback)

        # Fire startup
        coordinator.fire_startup()

        # Trigger shutdown
        coordinator._handle_sigterm(signal.SIGTERM, None)

        # Should see full lifecycle sequence
        assert len(events_received) == 4
        assert events_received[0] == LifecycleEvent.STARTUP
        assert events_received[1] == LifecycleEvent.PREPARE_SHUTDOWN
        assert events_received[2] == LifecycleEvent.SHUTDOWN
        assert events_received[3] == LifecycleEvent.AFTER_SHUTDOWN


class TestNoopLifecycleCoordinator:
    """Test no-op lifecycle coordinator for testing."""

    def test_initialization(self):
        """Test TestLifecycleCoordinator initialization."""
        coordinator = TestLifecycleCoordinator()

        assert not coordinator.is_shutting_down()
        assert len(coordinator._notifications) == 0
        assert len(coordinator._waiters) == 0

    def test_register_notification(self):
        """Test registering notification callbacks."""
        coordinator = TestLifecycleCoordinator()
        callback = MagicMock()

        coordinator.register_lifecycle_notification(callback)

        assert len(coordinator._notifications) == 1
        assert callback in coordinator._notifications

    def test_register_waiter(self):
        """Test registering shutdown waiters."""
        coordinator = TestLifecycleCoordinator()
        waiter = MagicMock()

        coordinator.register_shutdown_waiter("TestService", waiter)

        assert "TestService" in coordinator._waiters
        assert coordinator._waiters["TestService"] is waiter

    def test_handle_sigterm_simulation(self):
        """Test simulated shutdown behavior."""
        coordinator = TestLifecycleCoordinator()

        callback = MagicMock()
        waiter = MagicMock(return_value=True)

        coordinator.register_lifecycle_notification(callback)
        coordinator.register_shutdown_waiter("TestService", waiter)

        # Should not be shutting down initially
        assert not coordinator.is_shutting_down()

        # Simulate shutdown
        coordinator.simulate_full_shutdown()

        # Should now be shutting down
        assert coordinator.is_shutting_down()

        # Callback should be called twice (PREPARE_SHUTDOWN + SHUTDOWN)
        assert callback.call_count == 2
        callback.assert_any_call(LifecycleEvent.PREPARE_SHUTDOWN)
        callback.assert_any_call(LifecycleEvent.SHUTDOWN)

        # Waiter should be called once
        waiter.assert_called_once_with(30.0)

    def test_simulate_shutdown_method(self):
        """Test the simulate_shutdown convenience method."""
        coordinator = TestLifecycleCoordinator()

        assert not coordinator.is_shutting_down()

        coordinator.simulate_shutdown()

        assert coordinator.is_shutting_down()

    def test_simulate_startup_method(self):
        """Test the simulate_startup convenience method."""
        coordinator = TestLifecycleCoordinator()

        events_received = []

        def callback(event: LifecycleEvent):
            events_received.append(event)

        coordinator.register_lifecycle_notification(callback)

        coordinator.simulate_startup()

        assert len(events_received) == 1
        assert events_received[0] == LifecycleEvent.STARTUP

    def test_exception_handling_in_callbacks(self):
        """Test that TestLifecycleCoordinator handles exceptions in callbacks."""
        coordinator = TestLifecycleCoordinator()

        def bad_callback(event: LifecycleEvent):
            raise Exception("Test error")

        def good_callback(event: LifecycleEvent):
            good_callback.calls = getattr(good_callback, 'calls', [])
            good_callback.calls.append(event)

        coordinator.register_lifecycle_notification(bad_callback)
        coordinator.register_lifecycle_notification(good_callback)

        # Should not raise exception
        coordinator.simulate_full_shutdown()

        # Good callback should still be called
        assert len(good_callback.calls) == 2

    def test_exception_handling_in_waiters(self):
        """Test that TestLifecycleCoordinator handles exceptions in waiters."""
        coordinator = TestLifecycleCoordinator()

        def bad_waiter(timeout: float) -> bool:
            raise Exception("Waiter error")

        good_waiter_called = threading.Event()

        def good_waiter(timeout: float) -> bool:
            good_waiter_called.set()
            return True

        coordinator.register_shutdown_waiter("BadService", bad_waiter)
        coordinator.register_shutdown_waiter("GoodService", good_waiter)

        # Should not raise exception
        coordinator.simulate_full_shutdown()

        # Good waiter should have been called
        assert good_waiter_called.is_set()

    def test_interface_compatibility(self):
        """Test that TestLifecycleCoordinator has same interface as real coordinator."""
        noop = TestLifecycleCoordinator()

        # Check all required methods exist
        assert hasattr(noop, 'initialize')
        assert hasattr(noop, 'register_lifecycle_notification')
        assert hasattr(noop, 'register_shutdown_waiter')
        assert hasattr(noop, 'is_shutting_down')
        assert hasattr(noop, 'simulate_full_shutdown')
        assert hasattr(noop, 'fire_startup')

        # Check methods are callable
        assert callable(noop.initialize)
        assert callable(noop.register_lifecycle_notification)
        assert callable(noop.register_shutdown_waiter)
        assert callable(noop.is_shutting_down)
        assert callable(noop.simulate_full_shutdown)
        assert callable(noop.fire_startup)


class TestLifecycleIntegrationScenarios:
    """Test realistic shutdown scenarios."""

    def test_coordinated_service_shutdown(self):
        """Test coordinated shutdown with multiple services."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        # Track the sequence of events
        event_sequence = []

        # Service 1: Quick to prepare, quick to shutdown
        def service1_notification(event: LifecycleEvent):
            event_sequence.append(f"Service1:{event.value}")

        def service1_waiter(timeout: float) -> bool:
            event_sequence.append("Service1:waiter_complete")
            return True

        # Service 2: Needs time to complete work
        def service2_notification(event: LifecycleEvent):
            event_sequence.append(f"Service2:{event.value}")

        def service2_waiter(timeout: float) -> bool:
            time.sleep(0.1)  # Simulate cleanup work
            event_sequence.append("Service2:waiter_complete")
            return True

        coordinator.register_lifecycle_notification(service1_notification)
        coordinator.register_shutdown_waiter("Service1", service1_waiter)

        coordinator.register_lifecycle_notification(service2_notification)
        coordinator.register_shutdown_waiter("Service2", service2_waiter)

        # Trigger shutdown
        coordinator._handle_sigterm(signal.SIGTERM, None)

        # Verify expected sequence
        assert "Service1:prepare-shutdown" in event_sequence
        assert "Service2:prepare-shutdown" in event_sequence
        assert "Service1:waiter_complete" in event_sequence
        assert "Service2:waiter_complete" in event_sequence
        assert "Service1:shutdown" in event_sequence
        assert "Service2:shutdown" in event_sequence
        assert "Service1:after-shutdown" in event_sequence
        assert "Service2:after-shutdown" in event_sequence

        # All PREPARE_SHUTDOWN notifications should come before any waiters
        prepare_indices = [i for i, event in enumerate(event_sequence)
                          if "prepare-shutdown" in event]
        waiter_indices = [i for i, event in enumerate(event_sequence)
                         if "waiter_complete" in event]
        shutdown_indices = [i for i, event in enumerate(event_sequence)
                           if event.endswith("shutdown") and "prepare-" not in event]

        assert max(prepare_indices) < min(waiter_indices)
        assert max(waiter_indices) < min(shutdown_indices)

    def test_shutdown_with_mixed_service_behavior(self):
        """Test shutdown with services that behave differently."""
        coordinator = LifecycleCoordinator(graceful_shutdown_timeout=60)

        results = {
            'fast_service_notified': False,
            'slow_service_notified': False,
            'failing_service_notified': False,
            'fast_service_completed': False,
            'slow_service_completed': False,
            'failing_service_attempted': False,
            'after_shutdown_attempted': False
        }

        # Fast service - completes immediately
        def fast_notification(event: LifecycleEvent):
            results['fast_service_notified'] = True
            if event == LifecycleEvent.AFTER_SHUTDOWN:
                results['after_shutdown_attempted'] = True

        def fast_waiter(timeout: float) -> bool:
            results['fast_service_completed'] = True
            return True

        # Slow service - takes time but completes
        def slow_notification(event: LifecycleEvent):
            results['slow_service_notified'] = True

        def slow_waiter(timeout: float) -> bool:
            time.sleep(0.2)  # Simulate work
            results['slow_service_completed'] = True
            return True

        # Failing service - raises exception
        def failing_notification(event: LifecycleEvent):
            results['failing_service_notified'] = True

        def failing_waiter(timeout: float) -> bool:
            results['failing_service_attempted'] = True
            raise Exception("Service failure")

        coordinator.register_lifecycle_notification(fast_notification)
        coordinator.register_shutdown_waiter("FastService", fast_waiter)

        coordinator.register_lifecycle_notification(slow_notification)
        coordinator.register_shutdown_waiter("SlowService", slow_waiter)

        coordinator.register_lifecycle_notification(failing_notification)
        coordinator.register_shutdown_waiter("FailingService", failing_waiter)

        # Trigger shutdown
        coordinator._handle_sigterm(signal.SIGTERM, None)

        # All services should be notified
        assert results['fast_service_notified']
        assert results['slow_service_notified']
        assert results['failing_service_notified']

        # Fast and slow services should complete
        assert results['fast_service_completed']
        assert results['slow_service_completed']

        # Failing service should be attempted
        assert results['failing_service_attempted']

        # After shutdown should be raised
        assert results['after_shutdown_attempted']
