from .test_stdlib import run_and_capture


def test_apply_gravity():
    out = run_and_capture(
        """
        let vy = 0
        vy = apply_gravity(vy, 980, 0.1)
        print(vy)
        """
    )
    assert out.strip() == "98.0"


def test_apply_friction():
    out = run_and_capture(
        """
        let v = 100
        v = apply_friction(v, 0.9)
        print(v)
        """
    )
    assert out.strip() == "90.0"


def test_integrate():
    out = run_and_capture(
        """
        print(integrate(0, 50, 0.1))
        """
    )
    assert out.strip() == "5.0"


def test_clamp():
    out = run_and_capture(
        """
        print(clamp(15, 0, 10))
        print(clamp(-5, 0, 10))
        print(clamp(5, 0, 10))
        """
    )
    assert out.strip().splitlines() == ["10", "0", "5"]


def test_physics_step_semi_implicit_euler():
    out = run_and_capture(
        """
        let step = physics_step(0, 0, 10, 0, 0, 980, 0.1)
        print(step)
        """
    )
    # semi-implicit Euler: vy updates first (0 + 980*0.1 = 98), then
    # position uses the *new* velocity (0 + 98*0.1 = 9.8)
    assert "9.8" in out
    assert "98" in out


def test_physics_step_no_acceleration_is_plain_motion():
    out = run_and_capture(
        """
        let step = physics_step(0, 0, 5, 0, 0, 0, 1)
        print(step[0], step[2])
        """
    )
    assert out.strip() == "5.0 5.0"
