!> Numerical integration
!>
!> ...
module stdlib_quadrature
  use stdlib_kinds, only: sp, dp, qp
  implicit none
  private

  public :: trapz
  ! ...

  !> Integrates sampled values using trapezoidal rule
  interface trapz
    pure module function trapz_dx_dp(y, dx) result(integral)
      real(dp), intent(in) :: y(:)
      real(dp), intent(in) :: dx
      real(dp) :: integral
    end function trapz_dx_dp
    module function trapz_x_dp(y, x) result(integral)
      real(dp), intent(in) :: y(:)
      real(dp), intent(in) :: x(:)
      real(dp) :: integral
    end function trapz_x_dp
  end interface trapz

  ! ...
end module stdlib_quadrature