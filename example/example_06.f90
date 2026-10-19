!> Linear solvers showcasing the different flavours of interfaces.

module linear_solvers
  implicit none
  private

  public :: solve, norm, residual_callback, operator(.dot.)

  !> Solve the linear system :math:`A x = b` for any supported kind.
  !>
  !> The specific procedure is selected at compile time from the type of
  !> the arguments.
  interface solve
    module procedure solve_real, solve_complex
  end interface solve

  !> Vector norms, implemented in a submodule.
  interface norm
    !> Euclidean norm :math:`\|x\|_2`.
    pure module function norm_2(x) result(res)
      real, intent(in) :: x(:) !> Input vector
      real :: res !> Euclidean norm of ``x``
    end function norm_2
    !> Norm of order ``p``.
    pure module function norm_p(x, p) result(res)
      real, intent(in) :: x(:) !> Input vector
      integer, intent(in) :: p !> Order of the norm
      real :: res !> ``p``-norm of ``x``
    end function norm_p
  end interface norm

  !> Dot product operator: ``a .dot. b``.
  interface operator(.dot.)
    module procedure dot_real
  end interface operator(.dot.)

  abstract interface
    !> Signature of a user-supplied residual monitor, called once per iteration.
    subroutine residual_callback(iter, residual)
      integer, intent(in) :: iter !> Iteration number
      real, intent(in) :: residual !> Current residual norm
    end subroutine residual_callback
  end interface

contains

  !> Solve a real-valued system in place.
  subroutine solve_real(a, b)
    real, intent(in) :: a(:, :) !> System matrix
    real, intent(inout) :: b(:) !> Right-hand side, overwritten with the solution
  end subroutine solve_real

  !> Solve a complex-valued system in place.
  subroutine solve_complex(a, b)
    complex, intent(in) :: a(:, :) !> System matrix
    complex, intent(inout) :: b(:) !> Right-hand side, overwritten with the solution
  end subroutine solve_complex

  !> Dot product of two real vectors.
  pure function dot_real(a, b) result(res)
    real, intent(in) :: a(:) !> First vector
    real, intent(in) :: b(:) !> Second vector
    real :: res !> Dot product
    res = sum(a * b)
  end function dot_real

end module linear_solvers
