!> Simple test program
program test_program
    use math_utilities
    implicit none
    
    type(vector_type) :: v1, v2, v3
    
    !> Example usage
    !> :math:`\vec{v_3} = \vec{v_1} + \vec{v_2}`.
    v1 = vector_type(1.0, 2.0, 3.0)
    v2 = vector_type(4.0, 5.0, 6.0)
    v3 = vector_add(v1, v2)

    print *, "v3 =", v3%x, v3%y, v3%z

contains

    !> Internal helper function usage example
    pure function example_internal_procedure(v) result(y)
        type(vector_type), intent(in) :: v !> Input vector
        real :: y !> Output value
        
        ! Using the private helper function
        y = v%x**2 + v%y**2 + v%z**2
    end function example_internal_procedure
    
end program test_program