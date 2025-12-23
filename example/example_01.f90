module math_utils
  !> This module provides utilities for mathematical operations
  implicit none

  contains

  !# Preceding doc.
  !> Adds two integers and returns the result
  !> but the comment continues in the next line
  subroutine add_integers(a, b, c)
    
    !> The first integer to add
    integer, intent(in) :: a   
    !> The second integer to add
    integer, intent(in) :: b   
    !> The result of the addition
    integer, intent(out) :: c  
    c = a + b
  end subroutine add_integers

  !> Multiplies two real numbers and returns the result
  elemental function multiply_reals(x, y) result(res)
    real, intent(in) :: x   !> The first real number to multiply
    real, intent(in) :: y   !> The second real number to multiply
    real :: res  !> The result of the multiplication
    res = x * y
  end function multiply_reals
end module math_utils