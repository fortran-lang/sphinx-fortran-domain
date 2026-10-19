Interfaces
==========

This module groups procedures behind interfaces in all the common ways:

* ``solve`` is a generic interface over module procedures (``module procedure``),
* ``norm`` declares interface bodies whose implementation lives in a submodule,
* ``operator(.dot.)`` defines a user operator,
* ``residual_callback`` is an abstract interface.

Each interface lists the specific procedures it groups under *Procedures*.
Specifics that are private to the module are still documented, since they
are reachable through the public interface.

.. literalinclude:: ../../example/example_06.f90
    :language: Fortran
    :caption: example_06.f90

.. f:module:: linear_solvers

Declaring an interface by hand
------------------------------

The ``f:interface`` directive lists the specific procedures of the interface
of the same name in ``fortran_sources`` by default, so nothing needs to be
repeated. The ``:module:`` option picks the module (or submodule) to look in
when several of them define an interface with that name:

.. code-block:: rst

    .. f:interface:: trapz
        :module: stdlib_quadrature

        Integrates sampled values using the trapezoidal rule.

which renders as:

.. f:interface:: trapz
    :module: stdlib_quadrature

    Integrates sampled values using the trapezoidal rule.

Here ``trapz`` comes from ``example_04_parent_module.f90``. Its specifics are
not documented on any page, so they are listed without links.

The ``:procedures:`` option overrides that list, for instance to keep only
some of the specifics or to document an interface that is not parsed at all.
Names that the parsed interface does not contain are reported as warnings.
Each name links to its documentation, whether parsed or declared by hand:

.. code-block:: rst

    .. f:interface:: interpolate
        :procedures: interp_linear, interp_cubic

        Interpolate tabulated data at new abscissae.

    .. f:function:: interp_linear

        Piecewise-linear interpolation.

    .. f:function:: interp_cubic

        Cubic spline interpolation.

which renders as:

.. f:interface:: interpolate
    :procedures: interp_linear, interp_cubic

    Interpolate tabulated data at new abscissae.

.. f:function:: interp_linear

    Piecewise-linear interpolation.

.. f:function:: interp_cubic

    Cubic spline interpolation.
