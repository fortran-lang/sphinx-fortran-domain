!> Actual implementation of the trapezoidal integration rule
!>
!> ...
submodule (stdlib_quadrature) stdlib_quadrature_trapz
  use stdlib_error, only: check
  implicit none

contains

  pure module function trapz_dx_dp(y, dx) result(integral)
    real(dp), intent(in) :: y(:)
    real(dp), intent(in) :: dx
    real(dp) :: integral
    integer :: n

    n = size(y)
    select case (n)
    case (0:1)
      integral = 0.0_dp
    case (2)
      integral = 0.5_dp*dx*(y(1) + y(2))
    case default
      integral = dx*(sum(y(2:n-1)) + 0.5_dp*(y(1) + y(n)))
    end select
  end function trapz_dx_dp

  ! ...
end submodule stdlib_quadrature_trapz